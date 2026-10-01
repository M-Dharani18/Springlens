package com.rag.springlens;

import com.rag.springlens.chunking.FrameworkAwareTextSplitter;
import org.springframework.ai.document.Document;
import org.springframework.ai.transformer.splitter.TokenTextSplitter;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Stream;

@Service
public class ProjectIngestionService {

    private final VectorStore vectorStore;
    private final CodeChunkRepository codeChunkRepository;
    private final FrameworkAwareTextSplitter frameworkAwareTextSplitter;

    public ProjectIngestionService(VectorStore vectorStore, 
                                   CodeChunkRepository codeChunkRepository,
                                   FrameworkAwareTextSplitter frameworkAwareTextSplitter) {
        this.vectorStore = vectorStore;
        this.codeChunkRepository = codeChunkRepository;
        this.frameworkAwareTextSplitter = frameworkAwareTextSplitter;
    }

    public int ingestProject(String projectPath, String projectName, String strategy) throws IOException {
        Path root = Path.of(projectPath);
        List<Document> finalChunks = new ArrayList<>();

        try (Stream<Path> paths = Files.walk(root)) {
            List<Path> javaFiles = paths
                    .filter(p -> p.toString().endsWith(".java"))
                    .toList();

            for (Path file : javaFiles) {
                String content = Files.readString(file);
                String relativePath = root.relativize(file).toString();
                String fileName = file.getFileName().toString();

                if ("ast_framework".equalsIgnoreCase(strategy)) {
                    List<Document> astDocs = frameworkAwareTextSplitter.split(content, fileName);
                    for (Document d : astDocs) {
                        Map<String, Object> meta = d.getMetadata();
                        meta.put("project", projectName);
                        meta.put("filePath", relativePath);
                        meta.put("chunkingStrategy", "ast_framework");
                        finalChunks.add(d);
                    }
                } else {
                    Document doc = new Document(content, Map.of(
                            "project", projectName,
                            "filePath", relativePath,
                            "chunkingStrategy", "generic"
                    ));
                    TokenTextSplitter splitter = TokenTextSplitter.builder().withChunkSize(800).build();
                    finalChunks.addAll(splitter.apply(List.of(doc)));
                }
            }
        }

        vectorStore.add(finalChunks);

        for (Document chunk : finalChunks) {
            CodeChunkDocument esDoc = new CodeChunkDocument(
                    UUID.randomUUID().toString(),
                    chunk.getText(),
                    String.valueOf(chunk.getMetadata().getOrDefault("filePath", "unknown")),
                    projectName,
                    String.valueOf(chunk.getMetadata().getOrDefault("chunkingStrategy", strategy))
            );
            codeChunkRepository.save(esDoc);
        }

        return finalChunks.size();
    }
}
