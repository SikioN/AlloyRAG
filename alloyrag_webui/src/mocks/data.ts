// This file will contain the mock data for the API responses.

export const queryResponse = {
  // This is a sample response for the /query endpoint.
  // We will populate this with more realistic data based on the Pydantic models.
  "answer": "This is a mocked answer from the AlloyRAG system.",
  "context": [
    {
      "text": "This is a sample context document.",
      "doc_id": "doc1",
      "doc_metadata": {
        "filename": "sample.pdf"
      }
    }
  ]
};

export const paginatedDocsResponse = {
    "documents": [
      {
        "id": "doc_123456",
        "content_summary": "Research paper on machine learning",
        "content_length": 15240,
        "status": "processed",
        "created_at": "2025-03-31T12:34:56",
        "updated_at": "2025-03-31T12:35:30",
        "track_id": "upload_20250729_170612_abc123",
        "chunks_count": 12,
        "error_msg": null,
        "metadata": { "author": "John Doe", "year": 2025 },
        "file_path": "research_paper.pdf",
      },
      {
          "id": "doc_654321",
          "content_summary": "Financial report for Q2 2025",
          "content_length": 8000,
          "status": "processing",
          "created_at": "2025-04-01T10:00:00",
          "updated_at": "2025-04-01T10:05:00",
          "track_id": "upload_20250801_100000_def456",
          "chunks_count": 8,
          "error_msg": null,
          "metadata": { "report_type": "quarterly" },
          "file_path": "financial_report_q2_2025.docx",
      }
    ],
    "pagination": {
      "page": 1,
      "page_size": 10,
      "total_count": 2,
      "total_pages": 1,
      "has_next": false,
      "has_prev": false,
    },
    "status_counts": {
      "pending": 10,
      "processing": 5,
      "preprocessed": 5,
      "processed": 130,
      "failed": 5,
    },
  };

  export const knowledgeGraphResponse = {
    "nodes": [
      { "id": 1, "labels": ["Норникель"], "properties": { "original_labels": ["Company"], "description": "Горно-металлургическая компания", "entity_type": "ORGANIZATION", "stock_symbol": "GMKN" } },
      { "id": 2, "labels": ["Проект 'Феникс'"], "properties": { "original_labels": ["Project"], "description": "Проект по модернизации производственных мощностей", "entity_type": "PROJECT", "status": "active" } },
      { "id": 3, "labels": ["Искусственный интеллект"], "properties": { "original_labels": ["Technology", "Field"], "description": "Область компьютерных наук", "entity_type": "TECHNOLOGY" } },
      { "id": 4, "labels": ["RAG"], "properties": { "original_labels": ["Technology"], "description": "Retrieval-Augmented Generation", "entity_type": "TECHNOLOGY" } },
      { "id": 5, "labels": ["Добыча данных"], "properties": { "original_labels": ["Technology"], "description": "Data Mining", "entity_type": "TECHNOLOGY" } },
      { "id": 6, "labels": ["Иван Иванов"], "properties": { "original_labels": ["Person"], "description": "Руководитель проекта 'Феникс'", "entity_type": "PERSON", "role": "Project Manager" } },
      { "id": 7, "labels": ["Мария Петрова"], "properties": { "original_labels": ["Person"], "description": "Ведущий разработчик в AlloyRAG Inc.", "entity_type": "PERSON", "role": "Lead Developer" } },
      { "id": 8, "labels": ["Норильск"], "properties": { "original_labels": ["Location", "City"], "description": "Город в Красноярском крае", "entity_type": "LOCATION" } },
      { "id": 9, "labels": ["Москва"], "properties": { "original_labels": ["Location", "City"], "description": "Столица России", "entity_type": "LOCATION" } },
      { "id": 10, "labels": ["AlloyRAG Inc."], "properties": { "original_labels": ["Company", "Partner"], "description": "Технологический партнер", "entity_type": "ORGANIZATION" } }
    ],
    "edges": [
      { "id": "rel_1", "source": 1, "target": 8, "type": "LOCATED_IN", "properties": { "description": "Основное производство находится в Норильске" } },
      { "id": "rel_2", "source": 1, "target": 9, "type": "HAS_OFFICE_IN", "properties": { "description": "Центральный офис" } },
      { "id": "rel_3", "source": 1, "target": 2, "type": "DEVELOPS", "properties": { "description": "Развивает и финансирует" } },
      { "id": "rel_4", "source": 1, "target": 10, "type": "PARTNERS_WITH", "properties": { "description": "Стратегическое партнерство в области ИИ" } },
      { "id": "rel_5", "source": 2, "target": 3, "type": "USES", "properties": {} },
      { "id": "rel_6", "source": 2, "target": 4, "type": "USES", "properties": { "description": "Используется для системы ответов на вопросы" } },
      { "id": "rel_7", "source": 3, "target": 4, "type": "INCLUDES", "properties": {} },
      { "id": "rel_8", "source": 3, "target": 5, "type": "INCLUDES", "properties": {} },
      { "id": "rel_9", "source": 6, "target": 1, "type": "WORKS_AT", "properties": {} },
      { "id": "rel_10", "source": 6, "target": 2, "type": "MANAGES", "properties": {} },
      { "id": "rel_11", "source": 7, "target": 10, "type": "WORKS_AT", "properties": {} }
    ]
  };

  export const healthStatusResponse = {
    "status": "healthy",
    "working_directory": "/mock/working_dir",
    "input_directory": "/mock/input_dir",
    "configuration": {
      "llm_binding": "mock-llm",
      "llm_binding_host": "http://localhost:8080",
      "llm_model": "mock-model",
      "embedding_binding": "mock-embedding",
      "embedding_binding_host": "http://localhost:8081",
      "embedding_model": "mock-embedding-model",
      "kv_storage": "mock-kv",
      "doc_status_storage": "mock-doc-status",
      "graph_storage": "mock-graph",
      "vector_storage": "mock-vector",
    },
    "core_version": "0.1.0-mock",
    "api_version": "0.1.0-mock",
    "auth_mode": "disabled",
    "pipeline_busy": false,
    "pipeline_active": false,
  };

  export const uploadResponse = {
    "status": "success",
    "message": "File uploaded successfully.",
    "track_id": "mock_track_id_12345"
  };

  export const authStatusResponse = {
    "auth_configured": false,
    "auth_mode": "disabled",
    "message": "Authentication is disabled. Using guest access.",
    "core_version": "0.1.0-mock",
    "api_version": "0.1.0-mock",
    "webui_title": "AlloyRAG (Mocked)",
    "webui_description": "A mocked AlloyRAG instance for development."
  };

  export const popularLabelsResponse = [
    "Person",
    "Company",
    "Automotive",
    "Aerospace",
    "Entrepreneur"
  ];
  
  export const graphLabelListResponse = popularLabelsResponse.concat(["Technology", "Finance"]);
  
  export const allDocumentsResponse = {
    statuses: {
      processed: paginatedDocsResponse.documents,
    },
  };
  
  export const scanResponse = {
    status: "scanning_started",
    message: "Scanning for new documents has started.",
    track_id: "mock_scan_track_id_67890",
  };
  
  export const reprocessFailedResponse = {
    status: "reprocessing_started",
    message: "Reprocessing failed documents has started.",
    track_id: "mock_reprocess_track_id_11223",
  };
  
  export const scanProgressResponse = {
    is_scanning: false,
    current_file: "",
    indexed_count: 0,
    total_files: 0,
    progress: 100,
  };
  
  export const docActionResponse = {
    status: "success",
    message: "Action completed successfully.",
    track_id: "mock_action_track_id_55555",
  };
  
  export const deleteDocumentsResponse = {
    status: "deletion_started",
    message: "Document deletion process has started.",
    doc_id: "doc_123456",
  };
  
  export const clearCacheResponse = {
    status: "success",
    message: "Cache cleared successfully.",
  };
  
  export const pipelineStatusResponse = {
    autoscanned: true,
    busy: false,
    job_name: "idle",
    docs: 0,
    batchs: 0,
    cur_batch: 0,
    request_pending: false,
    latest_message: "Pipeline is idle.",
  };
  
  export const cancelPipelineResponse = {
    status: "not_busy",
    message: "Pipeline is not busy, nothing to cancel.",
  };
  
  export const loginResponse = {
    access_token: "mock-jwt-token-string",
    token_type: "bearer",
  };
  
  export const entityUpdateResponse = {
    status: "success",
    message: "Entity updated successfully.",
    data: {},
  };
  
  export const entityExistsResponse = {
    exists: false,
  };
  
  export const trackStatusResponse = {
    track_id: "mock_track_id_12345",
    documents: [paginatedDocsResponse.documents[0]],
    total_count: 1,
    status_summary: { processed: 1 },
  };
  
  export const statusCountsResponse = {
    status_counts: {
      pending: 10,
      processing: 5,
      preprocessed: 5,
      processed: 130,
      failed: 5,
    },
  };
