# app/services/elasticsearch_service.py

import logging
from typing import List, Dict, Any, Optional
from elasticsearch import AsyncElasticsearch
import re
import json
import os

from app.core.config import settings

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Параметры подключения к Elasticsearch
ES_HOST = "http://localhost:9200"
ES_USER = "elastic"
ES_PASS = "GIkb8BKzkXK7i2blnG2O"

# Индексы в Elasticsearch
ES_INDICES = {
    "court_decisions": "court_decisions_index",
    "court_reviews": "court_reviews_index",
    "legal_articles": "legal_articles_index",
    "ruslawod_chunks": "ruslawod_chunks_index"
}

class ElasticsearchService:
    """
    Сервис для работы с ElasticSearch
    """
    
    def __init__(self):
        self.es = AsyncElasticsearch([settings.ELASTICSEARCH_URL])
        self.indices = ES_INDICES
        self.law_index = "laws"
        self.court_decisions_index = "court_decisions"
        self.legal_analytics_index = "legal_analytics"
    
    async def search_law_chunks(
        self,
        query: str,
        top_n: int = 7
    ) -> List[Dict[str, Any]]:
        response = await self.es.search(
            index=self.law_index,
            body={
                "query": {
                    "multi_match": {
                        "query": query,
                        "fields": ["content^3", "title^2", "metadata.*"],
                        "type": "best_fields",
                        "tie_breaker": 0.3
                    }
                },
                "size": top_n
            }
        )
        
        return [
            {
                "id": hit["_id"],
                "score": hit["_score"],
                "content": hit["_source"]["content"],
                "title": hit["_source"]["title"],
                "metadata": hit["_source"].get("metadata", {})
            }
            for hit in response["hits"]["hits"]
        ]

    async def search_court_decisions(
        self,
        query: str,
        top_n: int = 7
    ) -> List[Dict[str, Any]]:
        response = await self.es.search(
            index=self.court_decisions_index,
            body={
                "query": {
                    "multi_match": {
                        "query": query,
                        "fields": ["content^3", "title^2", "metadata.*"],
                        "type": "best_fields",
                        "tie_breaker": 0.3
                    }
                },
                "size": top_n
            }
        )
        
        return [
            {
                "id": hit["_id"],
                "score": hit["_score"],
                "content": hit["_source"]["content"],
                "title": hit["_source"]["title"],
                "metadata": hit["_source"].get("metadata", {})
            }
            for hit in response["hits"]["hits"]
        ]

    async def search_legal_analytics(
        self,
        query: str,
        top_n: int = 5
    ) -> List[Dict[str, Any]]:
        response = await self.es.search(
            index=self.legal_analytics_index,
            body={
                "query": {
                    "multi_match": {
                        "query": query,
                        "fields": ["content^3", "title^2", "metadata.*"],
                        "type": "best_fields",
                        "tie_breaker": 0.3
                    }
                },
                "size": top_n
            }
        )
        
        return [
            {
                "id": hit["_id"],
                "score": hit["_score"],
                "content": hit["_source"]["content"],
                "title": hit["_source"]["title"],
                "metadata": hit["_source"].get("metadata", {})
            }
            for hit in response["hits"]["hits"]
        ]

    async def index_law_chunk(
        self,
        chunk_id: str,
        content: str,
        title: str,
        metadata: Dict[str, Any]
    ) -> None:
        await self.es.index(
            index=self.law_index,
            id=chunk_id,
            body={
                "content": content,
                "title": title,
                "metadata": metadata
            }
        )

    async def index_court_decision(
        self,
        decision_id: str,
        content: str,
        title: str,
        metadata: Dict[str, Any]
    ) -> None:
        await self.es.index(
            index=self.court_decisions_index,
            id=decision_id,
            body={
                "content": content,
                "title": title,
                "metadata": metadata
            }
        )

    async def index_legal_analytics(
        self,
        analytics_id: str,
        content: str,
        title: str,
        metadata: Dict[str, Any]
    ) -> None:
        await self.es.index(
            index=self.legal_analytics_index,
            id=analytics_id,
            body={
                "content": content,
                "title": title,
                "metadata": metadata
            }
        )

    async def close(self):
        await self.es.close()

# Создаем синглтон для использования в других модулях
elasticsearch_service = ElasticsearchService() 