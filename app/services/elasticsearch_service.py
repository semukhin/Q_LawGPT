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
    
    # app/services/elasticsearch_service.py - обновление методов
    async def search_law_chunks(
        self,
        query: str,
        top_n: int = 7
    ) -> List[Dict[str, Any]]:
        """
        Поиск по правовым нормам с объединенным запросом
        """
        try:
            # Создаем комбинированный запрос для лучшего поиска
            combined_query = {
                "query": {
                    "bool": {
                        "should": [
                            # Точное совпадение с запросом
                            {
                                "match_phrase": {
                                    "content": {
                                        "query": query,
                                        "boost": 3.0
                                    }
                                }
                            },
                            # Менее точное совпадение для расширенного поиска
                            {
                                "multi_match": {
                                    "query": query,
                                    "fields": ["content^3", "title^2", "metadata.*"],
                                    "type": "best_fields",
                                    "tie_breaker": 0.3,
                                    "fuzziness": "AUTO"
                                }
                            }
                        ],
                        "minimum_should_match": 1
                    }
                },
                "highlight": {
                    "fields": {
                        "content": {"number_of_fragments": 3, "fragment_size": 200},
                        "title": {}
                    },
                    "pre_tags": ["<em>"],
                    "post_tags": ["</em>"]
                },
                "size": top_n
            }
            
            response = await self.es.search(
                index=self.law_index,
                body=combined_query
            )
            
            results = []
            for hit in response["hits"]["hits"]:
                source = hit["_source"]
                highlights = hit.get("highlight", {})
                
                # Извлекаем выделенные фрагменты или используем исходный контент
                content_highlight = "".join(highlights.get("content", [source.get("content", "")[:500]]))
                title_highlight = "".join(highlights.get("title", [source.get("title", "")]))
                
                results.append({
                    "id": hit["_id"],
                    "score": hit["_score"],
                    "content": content_highlight,
                    "title": title_highlight,
                    "metadata": source.get("metadata", {})
                })
            
            return results
        except Exception as e:
            logger.error(f"Ошибка поиска в ElasticSearch: {str(e)}")
            return []

    async def hybrid_search(
        self,
        query: str,
        indices: List[str] = None,
        top_n: int = 10
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Комбинированный поиск по нескольким индексам
        """
        if indices is None:
            indices = [self.law_index, self.court_decisions_index, self.legal_analytics_index]
        
        results = {}
        
        try:
            for index in indices:
                # Используем тот же запрос, что и в search_law_chunks
                combined_query = {
                    "query": {
                        "bool": {
                            "should": [
                                {"match_phrase": {"content": {"query": query, "boost": 3.0}}},
                                {
                                    "multi_match": {
                                        "query": query,
                                        "fields": ["content^3", "title^2", "metadata.*"],
                                        "type": "best_fields",
                                        "tie_breaker": 0.3,
                                        "fuzziness": "AUTO"
                                    }
                                }
                            ],
                            "minimum_should_match": 1
                        }
                    },
                    "highlight": {
                        "fields": {
                            "content": {"number_of_fragments": 3, "fragment_size": 200},
                            "title": {}
                        },
                        "pre_tags": ["<em>"],
                        "post_tags": ["</em>"]
                    },
                    "size": top_n
                }
                
                response = await self.es.search(
                    index=index,
                    body=combined_query
                )
                
                index_results = []
                for hit in response["hits"]["hits"]:
                    source = hit["_source"]
                    highlights = hit.get("highlight", {})
                    
                    content_highlight = "".join(highlights.get("content", [source.get("content", "")[:500]]))
                    title_highlight = "".join(highlights.get("title", [source.get("title", "")]))
                    
                    index_results.append({
                        "id": hit["_id"],
                        "score": hit["_score"],
                        "content": content_highlight,
                        "title": title_highlight,
                        "metadata": source.get("metadata", {})
                    })
                
                results[index] = index_results
            
            return results
        except Exception as e:
            logger.error(f"Ошибка гибридного поиска: {str(e)}")
            return {index: [] for index in indices}

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