from elasticsearch import Elasticsearch, helpers
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class ElasticSearch:
    def __init__(self):
        self.es = Elasticsearch([settings.ELASTICSEARCH_URL])
        self._create_indices_if_not_exist()
    
    def _create_indices_if_not_exist(self):
        # Define indices for different document types
        indices = {
            "laws": {
                "settings": {
                    "analysis": {
                        "analyzer": {
                            "russian_custom": {
                                "type": "custom",
                                "tokenizer": "standard",
                                "filter": ["lowercase", "russian_stop", "russian_stemmer"]
                            }
                        },
                        "filter": {
                            "russian_stop": {
                                "type": "stop",
                                "stopwords": "_russian_"
                            },
                            "russian_stemmer": {
                                "type": "stemmer",
                                "language": "russian"
                            }
                        }
                    }
                },
                "mappings": {
                    "properties": {
                        "title": {"type": "text", "analyzer": "russian_custom"},
                        "content": {"type": "text", "analyzer": "russian_custom"},
                        "document_type": {"type": "keyword"},
                        "publication_date": {"type": "date"},
                        "source": {"type": "keyword"},
                        "vector_embedding": {"type": "dense_vector", "dims": 1536}
                    }
                }
            },
            "court_decisions": {
                "settings": {
                    "analysis": {
                        "analyzer": {
                            "russian_custom": {
                                "type": "custom",
                                "tokenizer": "standard",
                                "filter": ["lowercase", "russian_stop", "russian_stemmer"]
                            }
                        },
                        "filter": {
                            "russian_stop": {
                                "type": "stop",
                                "stopwords": "_russian_"
                            },
                            "russian_stemmer": {
                                "type": "stemmer",
                                "language": "russian"
                            }
                        }
                    }
                },
                "mappings": {
                    "properties": {
                        "case_number": {"type": "keyword"},
                        "title": {"type": "text", "analyzer": "russian_custom"},
                        "content": {"type": "text", "analyzer": "russian_custom"},
                        "court_name": {"type": "keyword"},
                        "decision_date": {"type": "date"},
                        "document_type": {"type": "keyword"},
                        "vector_embedding": {"type": "dense_vector", "dims": 1536}
                    }
                }
            },
            "legal_analytics": {
                "settings": {
                    "analysis": {
                        "analyzer": {
                            "russian_custom": {
                                "type": "custom",
                                "tokenizer": "standard",
                                "filter": ["lowercase", "russian_stop", "russian_stemmer"]
                            }
                        },
                        "filter": {
                            "russian_stop": {
                                "type": "stop",
                                "stopwords": "_russian_"
                            },
                            "russian_stemmer": {
                                "type": "stemmer",
                                "language": "russian"
                            }
                        }
                    }
                },
                "mappings": {
                    "properties": {
                        "title": {"type": "text", "analyzer": "russian_custom"},
                        "content": {"type": "text", "analyzer": "russian_custom"},
                        "author": {"type": "keyword"},
                        "publication_date": {"type": "date"},
                        "source": {"type": "keyword"},
                        "document_type": {"type": "keyword"},
                        "vector_embedding": {"type": "dense_vector", "dims": 1536}
                    }
                }
            }
        }
        
        # Create indices if they don't exist
        for index_name, index_config in indices.items():
            if not self.es.indices.exists(index=index_name):
                try:
                    self.es.indices.create(index=index_name, body=index_config)
                    logger.info(f"Created index: {index_name}")
                except Exception as e:
                    logger.error(f"Error creating index {index_name}: {str(e)}")
    
    def search(self, index, query, size=10):
        """
        Perform search on specified index
        """
        try:
            result = self.es.search(index=index, body=query, size=size)
            return result
        except Exception as e:
            logger.error(f"Error searching {index}: {str(e)}")
            return {"error": str(e)}
    
    def bulk_index(self, index, documents):
        """
        Bulk index documents
        """
        actions = [
            {
                "_index": index,
                "_source": doc
            }
            for doc in documents
        ]
        
        try:
            success, failed = helpers.bulk(self.es, actions, stats_only=True)
            logger.info(f"Indexed {success} documents, {failed} failed")
            return {"success": success, "failed": failed}
        except Exception as e:
            logger.error(f"Error bulk indexing to {index}: {str(e)}")
            return {"error": str(e)}
    
    def hybrid_search(self, index, text_query, vector_query, text_weight=0.7, vector_weight=0.3, size=10):
        """
        Perform hybrid search combining text and vector search
        """
        query = {
            "query": {
                "script_score": {
                    "query": {
                        "match": {
                            "content": text_query
                        }
                    },
                    "script": {
                        "source": f"""
                            double text_score = _score * {text_weight};
                            double vector_score = cosineSimilarity(params.query_vector, 'vector_embedding') * {vector_weight};
                            return text_score + vector_score;
                        """,
                        "params": {
                            "query_vector": vector_query
                        }
                    }
                }
            }
        }
        
        return self.search(index, query, size)

# Singleton instance
elastic_search = ElasticSearch()