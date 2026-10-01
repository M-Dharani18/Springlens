package com.rag.springlens;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.prompt.ChatOptions;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.bind.annotation.*;

import java.io.IOException;
import java.util.*;

@RestController
@RequestMapping("/api/test")
public class TestRagController {

    private static final int MAX_CHUNKS_PER_FILE = 2;
    private static final int FINAL_TOP_K = 5;
    private static final int CANDIDATE_POOL_SIZE = 40; // widened from 20 — gives the filter more to work with
    // Max unique source files we want in the final context window, caps both diversification + stitching combined
    private static final int MAX_UNIQUE_FILES = 5;

    private final VectorStore vectorStore;
    private final ProjectIngestionService ingestionService;
    private final ElasticsearchOperations elasticsearchOperations;
    private final ChatClient chatClient;

    public TestRagController(VectorStore vectorStore,
                             ProjectIngestionService ingestionService,
                             ElasticsearchOperations elasticsearchOperations,
                             @Qualifier("googleGenAiChatModel") ChatModel chatModel) {
        this.vectorStore = vectorStore;
        this.ingestionService = ingestionService;
        this.elasticsearchOperations = elasticsearchOperations;
        this.chatClient = ChatClient.create(chatModel);
    }

    private String cleanPreview(String text) {
        if (text == null) return "";
        String stripped = text.replaceFirst("(?s)^/\\*.*?\\*/\\s*", "");
        return stripped.substring(0, Math.min(300, stripped.length())) + "...";
    }

    // perFileCount is passed in so stitching respects the same per-file budget already used during diversification.
    // This prevents stitching from re-introducing duplicate file paths that the diversification step excluded.
    private List<Document> stitchClassContext(List<Document> selected, String strategy,
                                               Map<String, Integer> perFileCount, String project) {
        if (!"ast_framework".equals(strategy)) return selected;

        Set<String> classesAlreadyCovered = new HashSet<>();
        for (Document d : selected) {
            if ("CLASS_SUMMARY".equals(d.getMetadata().get("chunkType"))) {
                classesAlreadyCovered.add(String.valueOf(d.getMetadata().get("className")));
            }
        }

        List<Document> stitched = new ArrayList<>(selected);
        for (Document doc : selected) {
            if (!"METHOD_DECLARATION".equals(doc.getMetadata().get("chunkType"))) continue;
            String className = String.valueOf(doc.getMetadata().getOrDefault("className", ""));
            if (className.isEmpty() || classesAlreadyCovered.contains(className)) continue;

            // Don't stitch if we've already hit the global unique-file budget
            long uniqueFiles = perFileCount.values().stream().filter(c -> c > 0).count();
            if (uniqueFiles >= MAX_UNIQUE_FILES) break;

            try {
                String filterExpr = "chunkingStrategy == 'ast_framework' && chunkType == 'CLASS_SUMMARY'";
                if (project != null && !project.isEmpty()) {
                    filterExpr += " && project == '" + project + "'";
                }
                List<Document> classSummaryMatch = vectorStore.similaritySearch(
                        SearchRequest.builder()
                                .query(className)
                                .topK(3)
                                .filterExpression(filterExpr)
                                .build()
                );
                for (Document candidate : classSummaryMatch) {
                    if (className.equals(String.valueOf(candidate.getMetadata().get("className")))) {
                        String candidatePath = String.valueOf(candidate.getMetadata().getOrDefault("filePath", "unknown"));
                        int existingCount = perFileCount.getOrDefault(candidatePath, 0);
                        if (existingCount < MAX_CHUNKS_PER_FILE) {
                            stitched.add(candidate);
                            perFileCount.put(candidatePath, existingCount + 1);
                            classesAlreadyCovered.add(className);
                        }
                        break;
                    }
                }
            } catch (Exception e) {
                System.err.println("[STITCH_WARN] Failed to stitch class context for " + className + ": " + e.getMessage());
            }
        }
        return stitched;
    }

    private Map<String, Object> toResultMap(Document doc) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("filePath", String.valueOf(doc.getMetadata().getOrDefault("filePath", "unknown")));
        result.put("chunkingStrategy", String.valueOf(doc.getMetadata().getOrDefault("chunkingStrategy", "unknown")));
        result.put("architecturalLayer", String.valueOf(doc.getMetadata().getOrDefault("architecturalLayer", "GENERAL_COMPONENT")));
        result.put("chunkType", String.valueOf(doc.getMetadata().getOrDefault("chunkType", "unknown")));
        result.put("preview", cleanPreview(doc.getText()));
        result.put("fullText", doc.getText());
        return result;
    }

    @PostMapping("/ingest-project")
    public Map<String, Object> ingestProject(
            @RequestParam String path,
            @RequestParam String projectName,
            @RequestParam(defaultValue = "generic") String strategy) throws IOException {
        int chunkCount = ingestionService.ingestProject(path, projectName, strategy);
        return Map.of("project", projectName, "strategy", strategy, "chunksStored", chunkCount);
    }

    @GetMapping("/search")
    public List<Map<String, Object>> search(@RequestParam String query,
                                             @RequestParam String strategy,
                                             @RequestParam(required = false) String project) {
        String filterExpr = "chunkingStrategy == '" + strategy + "'";
        if (project != null && !project.isEmpty()) {
            filterExpr += " && project == '" + project + "'";
        }
        List<Document> candidates = vectorStore.similaritySearch(
                SearchRequest.builder()
                        .query(query)
                        .topK(CANDIDATE_POOL_SIZE)
                        .filterExpression(filterExpr)
                        .build()
        );

        // DIAGNOSTIC LOGGING — if this ever prints 0, we have concrete evidence of a
        // filter/embedding miss for this exact query+strategy+project combination, not a guess.
        System.out.println("[SEARCH_DIAG] query='" + query + "' strategy='" + strategy
                + "' project='" + project + "' rawCandidates=" + candidates.size());

        Map<String, Integer> perFileCount = new HashMap<>();
        List<Document> diversified = new ArrayList<>();
        for (Document doc : candidates) {
            String filePath = String.valueOf(doc.getMetadata().getOrDefault("filePath", "unknown"));
            int count = perFileCount.getOrDefault(filePath, 0);
            if (count < MAX_CHUNKS_PER_FILE) {
                diversified.add(doc);
                perFileCount.put(filePath, count + 1);
            }
            if (diversified.size() >= FINAL_TOP_K) break;
        }

        List<Document> stitched = stitchClassContext(diversified, strategy, perFileCount, project);
        System.out.println("[SEARCH_DIAG] afterDiversityAndStitch=" + stitched.size());

        return stitched.stream().map(this::toResultMap).toList();
    }

    @GetMapping("/search-hybrid")
    public List<Map<String, Object>> searchHybrid(@RequestParam String query,
                                                   @RequestParam String strategy,
                                                   @RequestParam(required = false) String project) {
        String denseFilterExpr = "chunkingStrategy == '" + strategy + "'";
        if (project != null && !project.isEmpty()) {
            denseFilterExpr += " && project == '" + project + "'";
        }
        List<Document> denseResults = vectorStore.similaritySearch(
                SearchRequest.builder().query(query).topK(CANDIDATE_POOL_SIZE)
                        .filterExpression(denseFilterExpr)
                        .build()
        );

        // BM25 also filters by project if provided
        Query esQuery;
        if (project != null && !project.isEmpty()) {
            esQuery = Query.of(q -> q.bool(b -> b
                    .must(m -> m.match(mm -> mm.field("content").query(query)))
                    .filter(f -> f.match(mm -> mm.field("chunkingStrategy").query(strategy)))
                    .filter(f -> f.match(mm -> mm.field("project").query(project)))
            ));
        } else {
            esQuery = Query.of(q -> q.bool(b -> b
                    .must(m -> m.match(mm -> mm.field("content").query(query)))
                    .filter(f -> f.match(mm -> mm.field("chunkingStrategy").query(strategy)))
            ));
        }
        NativeQuery nativeQuery = NativeQuery.builder().withQuery(esQuery).withMaxResults(CANDIDATE_POOL_SIZE).build();
        SearchHits<CodeChunkDocument> bm25Results = elasticsearchOperations.search(nativeQuery, CodeChunkDocument.class);

        System.out.println("[HYBRID_DIAG] query='" + query + "' strategy='" + strategy
                + "' project='" + project + "' denseCandidates=" + denseResults.size() + " bm25Candidates=" + bm25Results.getTotalHits());

        int k = 60;
        Map<String, Double> rrfScores = new HashMap<>();
        Map<String, Document> denseDocMap = new HashMap<>();
        Map<String, String> filePathByKey = new HashMap<>();

        for (int rank = 0; rank < denseResults.size(); rank++) {
            Document doc = denseResults.get(rank);
            String filePath = String.valueOf(doc.getMetadata().getOrDefault("filePath", "unknown"));
            String key = filePath + "::" + doc.getText().hashCode();
            rrfScores.merge(key, 1.0 / (k + rank + 1), Double::sum);
            denseDocMap.put(key, doc);
            filePathByKey.put(key, filePath);
        }

        int rank = 0;
        for (SearchHit<CodeChunkDocument> hit : bm25Results) {
            CodeChunkDocument doc = hit.getContent();
            String key = doc.getFilePath() + "::" + doc.getContent().hashCode();
            rrfScores.merge(key, 1.0 / (k + rank + 1), Double::sum);
            filePathByKey.put(key, doc.getFilePath());
            rank++;
        }

        List<Map.Entry<String, Double>> sortedEntries = rrfScores.entrySet().stream()
                .sorted((a, b) -> Double.compare(b.getValue(), a.getValue()))
                .toList();

        Map<String, Integer> perFileCount = new HashMap<>();
        List<Document> selectedDocs = new ArrayList<>();
        List<String> fallbackEntries = new ArrayList<>();

        for (Map.Entry<String, Double> e : sortedEntries) {
            String filePath = filePathByKey.get(e.getKey());
            int count = perFileCount.getOrDefault(filePath, 0);
            if (count >= MAX_CHUNKS_PER_FILE) continue;

            Document d = denseDocMap.get(e.getKey());
            if (d != null) {
                selectedDocs.add(d);
            } else {
                fallbackEntries.add(filePath);
            }
            perFileCount.put(filePath, count + 1);
            if (selectedDocs.size() + fallbackEntries.size() >= FINAL_TOP_K) break;
        }

        List<Document> stitched = stitchClassContext(selectedDocs, strategy, perFileCount, project);
        System.out.println("[HYBRID_DIAG] afterFusionDiversityStitch=" + (stitched.size() + fallbackEntries.size()));

        List<Map<String, Object>> finalResults = new ArrayList<>();
        for (Document d : stitched) {
            finalResults.add(toResultMap(d));
        }
        for (String filePath : fallbackEntries) {
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("filePath", filePath);
            result.put("chunkingStrategy", strategy);
            result.put("architecturalLayer", "GENERAL_COMPONENT");
            result.put("chunkType", "unknown");
            result.put("preview", "BM25 Direct Hit");
            result.put("fullText", "");
            finalResults.add(result);
        }

        return finalResults;
    }

    // ── Retrieval-only endpoint (no LLM, no Gemini calls) ────────────────────
    // Python evaluation scripts call this to get context chunks, then call Gemini
    // directly with their own rate-limiting. This avoids Spring AI retry burning quota.
    @GetMapping("/retrieve")
    public Map<String, Object> retrieve(
            @RequestParam String query,
            @RequestParam(defaultValue = "dense") String retrievalMode,
            @RequestParam(defaultValue = "generic") String strategy,
            @RequestParam(defaultValue = "C1") String condition,
            @RequestParam(required = false) String project) {

        List<Map<String, Object>> chunks =
                retrievalMode.equalsIgnoreCase("dense")
                        ? search(query, strategy, project)
                        : searchHybrid(query, strategy, project);

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("query", query);
        result.put("condition", condition);
        result.put("retrievalMode", retrievalMode);
        result.put("strategy", strategy);
        result.put("project", project);
        result.put("chunkCount", chunks.size());
        result.put("chunks", chunks);
        return result;
    }

    @GetMapping("/explain")
    public Map<String, Object> explain(
            @RequestParam String query,
            @RequestParam(defaultValue = "hybrid") String retrievalMode,
            @RequestParam(defaultValue = "generic") String strategy,
            @RequestParam(defaultValue = "c4") String condition,
            @RequestParam(required = false) String project) {

        List<Map<String, Object>> retrievedChunks =
                retrievalMode.equalsIgnoreCase("dense") ? search(query, strategy, project) : searchHybrid(query, strategy, project);

        // CRITICAL GUARD — never send empty context to the LLM and label it "grounded".
        // Prevents silent hallucination from contaminating results, live demos, or the dataset.
        if (retrievedChunks.isEmpty()) {
            System.err.println("[EXPLAIN_EMPTY] condition=" + condition + " strategy=" + strategy
                    + " mode=" + retrievalMode + " query='" + query + "' — SKIPPING generation.");
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("query", query);
            result.put("condition", condition);
            result.put("retrievalMode", retrievalMode);
            result.put("strategy", strategy);
            result.put("answer", null);
            result.put("error", "RETRIEVAL_EMPTY: No chunks matched strategy='" + strategy
                    + "' for this query. Generation was skipped to avoid ungrounded hallucination.");
            result.put("sources", retrievedChunks);
            return result;
        }

        StringBuilder context = new StringBuilder();
        for (Map<String, Object> chunk : retrievedChunks) {
            context.append("File: ").append(chunk.get("filePath")).append("\n");
            context.append("Architectural Metadata: Layer=").append(chunk.get("architecturalLayer"))
                    .append(", Strategy=").append(chunk.get("chunkingStrategy")).append("\n");
            context.append(chunk.get("fullText")).append("\n\n----------------------------------------\n\n");
        }

        String promptText = """
            You are an expert Spring Boot architect explaining code architecture to a developer.
            Use ONLY the following retrieved code context to answer. If the context doesn't
            fully answer the question, state what is missing rather than inventing details.
            When the retrieved context includes fields such as "Architectural Layer",
            "Implements", "Extends", or "Injected Dependencies", use those exact terms in
            your answer where relevant, rather than paraphrasing them.

            Retrieved Context:
            %s

            Developer Question: %s

            Provide a concise, grounded architectural explanation (max 250 words).
            """.formatted(context.toString(), query);

        ChatOptions options = ChatOptions.builder()
                .temperature(0.0)
                .build();

        String answer;
        try {
            answer = chatClient.prompt()
                    .user(promptText)
                    .options(options)
                    .call()
                    .content();
        } catch (Exception llmEx) {
            // Return a structured error instead of HTTP 500 so callers can handle gracefully
            String errMsg = llmEx.getMessage() != null ? llmEx.getMessage() : llmEx.getClass().getSimpleName();
            System.err.println("[LLM_ERROR] condition=" + condition + " strategy=" + strategy
                    + " query='" + query + "' — " + errMsg);
            Map<String, Object> errResult = new LinkedHashMap<>();
            errResult.put("query", query);
            errResult.put("condition", condition);
            errResult.put("retrievalMode", retrievalMode);
            errResult.put("strategy", strategy);
            errResult.put("project", project);
            errResult.put("answer", null);
            errResult.put("error", "LLM_ERROR: " + errMsg);
            errResult.put("sources", retrievedChunks);  // ← return chunks so Python can regen
            return errResult;
        }

        // Deduplicate sources_retrieved by filePath before returning
        Set<String> seenPaths = new LinkedHashSet<>();
        List<Map<String, Object>> deduplicatedChunks = new ArrayList<>();
        for (Map<String, Object> chunk : retrievedChunks) {
            String fp = String.valueOf(chunk.get("filePath"));
            if (seenPaths.add(fp)) {
                deduplicatedChunks.add(chunk);
            }
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("query", query);
        result.put("condition", condition);
        result.put("retrievalMode", retrievalMode);
        result.put("strategy", strategy);
        result.put("project", project);
        result.put("answer", answer);
        result.put("sources", deduplicatedChunks);
        return result;
    }

    @GetMapping("/compare-all")
    public Map<String, Object> compareAll(@RequestParam String query,
                                          @RequestParam(required = false) String project) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("query", query);
        String[][] combos = {{"C1", "generic", "dense"}, {"C2", "generic", "hybrid"},
                {"C3", "ast_framework", "dense"}, {"C4", "ast_framework", "hybrid"}};
        for (String[] combo : combos) {
            result.put(combo[0], explain(query, combo[2], combo[1], combo[0], project));
        }
        return result;
    }
}