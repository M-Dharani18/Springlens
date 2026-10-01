package com.rag.springlens;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;

@Document(indexName = "code_chunks")
public class CodeChunkDocument {

    @Id
    private String id;
    private String content;
    private String filePath;
    private String project;
    private String chunkingStrategy;

    public CodeChunkDocument() {}

    public CodeChunkDocument(String id, String content, String filePath, String project, String chunkingStrategy) {
        this.id = id;
        this.content = content;
        this.filePath = filePath;
        this.project = project;
        this.chunkingStrategy = chunkingStrategy;
    }

    // Getters and setters
    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getContent() { return content; }
    public void setContent(String content) { this.content = content; }
    public String getFilePath() { return filePath; }
    public void setFilePath(String filePath) { this.filePath = filePath; }
    public String getProject() { return project; }
    public void setProject(String project) { this.project = project; }
    public String getChunkingStrategy() { return chunkingStrategy; }
    public void setChunkingStrategy(String chunkingStrategy) { this.chunkingStrategy = chunkingStrategy; }
}