package com.rag.springlens.chunking;

import org.junit.jupiter.api.Test;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

public class AstChunkerTest {

    @Test
    public void testFrameworkAwareChunking() {
        String sampleController = """
            package com.example.demo;

            import org.springframework.web.bind.annotation.RestController;
            import org.springframework.web.bind.annotation.GetMapping;
            import org.springframework.beans.factory.annotation.Autowired;

            @RestController
            public class SampleController {

                @Autowired
                private Object sampleService;

                @GetMapping("/hello")
                public String hello() {
                    return "Hello World";
                }
            }
            """;

        List<AstChunker.AstChunk> chunks = AstChunker.parseAndChunk(sampleController, "SampleController.java");

        assertFalse(chunks.isEmpty());
        
        AstChunker.AstChunk summaryChunk = chunks.get(0);
        assertEquals("CLASS_SUMMARY", summaryChunk.getMetadata().get("chunkType"));
        assertEquals("WEB_PRESENTATION", summaryChunk.getMetadata().get("architecturalLayer"));
        assertTrue(summaryChunk.getContent().contains("[SPRING ARCHITECTURAL METADATA]"));

        AstChunker.AstChunk methodChunk = chunks.get(1);
        assertEquals("METHOD_DECLARATION", methodChunk.getMetadata().get("chunkType"));
        assertTrue(methodChunk.getContent().contains("hello()"));
    }
}
