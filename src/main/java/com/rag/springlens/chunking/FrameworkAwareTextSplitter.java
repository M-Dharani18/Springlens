package com.rag.springlens.chunking;

import org.springframework.ai.document.Document;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.stream.Collectors;

@Component
public class FrameworkAwareTextSplitter {

    public List<Document> split(String sourceCode, String fileName) {
        List<AstChunker.AstChunk> chunks = AstChunker.parseAndChunk(sourceCode, fileName);
        return chunks.stream()
                .map(AstChunker.AstChunk::toDocument)
                .collect(Collectors.toList());
    }
}
