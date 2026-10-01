package com.rag.springlens;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface CodeChunkRepository extends ElasticsearchRepository<CodeChunkDocument, String> {

}
