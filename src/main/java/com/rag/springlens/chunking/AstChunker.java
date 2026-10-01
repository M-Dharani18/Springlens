package com.rag.springlens.chunking;

import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.expr.MethodCallExpr;
import org.springframework.ai.document.Document;

import java.util.*;

public class AstChunker {

    public static class AstChunk {
        private final String content;
        private final Map<String, Object> metadata;

        public AstChunk(String content, Map<String, Object> metadata) {
            this.content = content;
            this.metadata = metadata;
        }

        public String getContent() { return content; }
        public Map<String, Object> getMetadata() { return metadata; }

        public Document toDocument() {
            return new Document(content, metadata);
        }
    }

    public static List<AstChunk> parseAndChunk(String sourceCode, String fileName) {
        List<AstChunk> chunks = new ArrayList<>();
        try {
            CompilationUnit cu = StaticJavaParser.parse(sourceCode);

            cu.findAll(ClassOrInterfaceDeclaration.class).forEach(classDecl -> {
                Map<String, Object> classMeta = SpringMetadataExtractor.extractClassMetadata(classDecl, fileName);

                // 1. Class-Level Summary Chunk
                StringBuilder classSummary = new StringBuilder();
                classSummary.append("Class Declaration: ").append(classDecl.getNameAsString()).append("\n");
                classDecl.getComment().ifPresent(c -> classSummary.append("Javadoc: ").append(c.getContent()).append("\n"));
                
                String classHeader = SpringMetadataExtractor.buildHeader(classMeta, "CLASS_SUMMARY", classDecl.getNameAsString());
                Map<String, Object> chunkMeta = new HashMap<>(classMeta);
                chunkMeta.put("chunkType", "CLASS_SUMMARY");
                chunkMeta.put("unitName", classDecl.getNameAsString());
                
                chunks.add(new AstChunk(classHeader + classSummary.toString(), chunkMeta));

                // Pre-index all methods declared in this class for sibling lookup
                Map<String, List<MethodDeclaration>> siblingMethodsByName = new HashMap<>();
                for (MethodDeclaration m : classDecl.getMethods()) {
                    siblingMethodsByName.computeIfAbsent(m.getNameAsString(), k -> new ArrayList<>()).add(m);
                }

                // 2. Method-Level Structural Chunks (With Sibling Method Stitching)
                for (MethodDeclaration method : classDecl.getMethods()) {
                    String methodSig = method.getSignature().asString();
                    String methodHeader = SpringMetadataExtractor.buildHeader(classMeta, "METHOD_DECLARATION", methodSig);
                    
                    Map<String, Object> methodMeta = new HashMap<>(classMeta);
                    methodMeta.put("chunkType", "METHOD_DECLARATION");
                    methodMeta.put("unitName", methodSig);
                    method.getBegin().ifPresent(b -> methodMeta.put("startLine", b.line));
                    method.getEnd().ifPresent(e -> methodMeta.put("endLine", e.line));

                    StringBuilder fullMethodText = new StringBuilder(methodHeader);
                    fullMethodText.append(method.toString());

                    // Call-graph analysis: find all internal helper method invocations
                    List<MethodCallExpr> callExprs = method.findAll(MethodCallExpr.class);
                    Set<String> attachedSiblings = new HashSet<>();
                    int stitchedCount = 0;

                    for (MethodCallExpr call : callExprs) {
                        String calledName = call.getNameAsString();
                        // Avoid self-recursion and duplicate attachment
                        if (!calledName.equals(method.getNameAsString()) && !attachedSiblings.contains(calledName)) {
                            List<MethodDeclaration> matches = siblingMethodsByName.get(calledName);
                            if (matches != null && !matches.isEmpty()) {
                                attachedSiblings.add(calledName);
                                for (MethodDeclaration sibling : matches) {
                                    fullMethodText.append("\n\n// --- SIBLING HELPER METHOD IN ")
                                                  .append(classDecl.getNameAsString())
                                                  .append(": ")
                                                  .append(sibling.getSignature().asString())
                                                  .append(" ---\n")
                                                  .append(sibling.toString());
                                    stitchedCount++;
                                }
                            }
                        }
                    }

                    methodMeta.put("hasSiblingHelpers", stitchedCount > 0);
                    methodMeta.put("siblingHelperCount", stitchedCount);

                    chunks.add(new AstChunk(fullMethodText.toString(), methodMeta));
                }
            });

            if (chunks.isEmpty()) {
                Map<String, Object> fallbackMeta = new HashMap<>();
                fallbackMeta.put("fileName", fileName);
                fallbackMeta.put("chunkType", "FALLBACK_TEXT");
                fallbackMeta.put("architecturalLayer", "GENERAL_COMPONENT");
                chunks.add(new AstChunk(sourceCode, fallbackMeta));
            }

        } catch (Exception e) {
            Map<String, Object> fallbackMeta = new HashMap<>();
            fallbackMeta.put("fileName", fileName);
            fallbackMeta.put("chunkType", "FALLBACK_TEXT");
            fallbackMeta.put("architecturalLayer", "GENERAL_COMPONENT");
            chunks.add(new AstChunk(sourceCode, fallbackMeta));
        }

        return chunks;
    }
}
