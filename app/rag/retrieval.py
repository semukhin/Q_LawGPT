from typing import List, Dict, Any, Optional
from app.rag.elastic import elastic_search
import logging
from sqlalchemy.orm import Session
import sqlalchemy as sa
from app.core.database import get_rag_db

logger = logging.getLogger(__name__)

class DocumentRetriever:
    def __init__(self):
        self.es = elastic_search
    
    def search_laws(self, query: str, size: int = 5) -> List[Dict[str, Any]]:
        """
        Search for laws related to the query
        """
        search_query = {
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": ["title^2", "content"],
                    "type": "best_fields",
                    "fuzziness": "AUTO"
                }
            },
            "highlight": {
                "fields": {
                    "title": {},
                    "content": {}
                }
            }
        }
        
        result = self.es.search("laws", search_query, size)
        return self._format_search_results(result)
    
    def search_court_decisions(self, query: str, size: int = 5) -> List[Dict[str, Any]]:
        """
        Search for court decisions related to the query
        """
        search_query = {
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": ["title^2", "content", "court_name"],
                    "type": "best_fields",
                    "fuzziness": "AUTO"
                }
            },
            "highlight": {
                "fields": {
                    "title": {},
                    "content": {}
                }
            }
        }
        
        result = self.es.search("court_decisions", search_query, size)
        return self._format_search_results(result)
    
    def search_legal_analytics(self, query: str, size: int = 5) -> List[Dict[str, Any]]:
        """
        Search for legal analytics related to the query
        """
        search_query = {
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": ["title^2", "content", "author"],
                    "type": "best_fields",
                    "fuzziness": "AUTO"
                }
            },
            "highlight": {
                "fields": {
                    "title": {},
                    "content": {}
                }
            }
        }
        
        result = self.es.search("legal_analytics", search_query, size)
        return self._format_search_results(result)
    
    def _format_search_results(self, result: Dict) -> List[Dict[str, Any]]:
        """
        Format search results for agent consumption
        """
        if "error" in result:
            logger.error(f"Search error: {result['error']}")
            return []
        
        formatted_results = []
        for hit in result.get("hits", {}).get("hits", []):
            source = hit.get("_source", {})
            highlights = hit.get("highlight", {})
            
            # Extract highlighted content or use original content
            content_highlight = "".join(highlights.get("content", [source.get("content", "")[:500]]))
            title_highlight = "".join(highlights.get("title", [source.get("title", "")]))
            
            formatted_result = {
                "id": hit.get("_id"),
                "title": title_highlight,
                "content_snippet": content_highlight,
                "score": hit.get("_score"),
                **source
            }
            
            formatted_results.append(formatted_result)
        
        return formatted_results
    
    def search_all(self, query: str, size_per_index: int = 3) -> Dict[str, List[Dict[str, Any]]]:
        """
        Search across all indices
        """
        laws = self.search_laws(query, size_per_index)
        court_decisions = self.search_court_decisions(query, size_per_index)
        legal_analytics = self.search_legal_analytics(query, size_per_index)
        
        return {
            "laws": laws,
            "court_decisions": court_decisions,
            "legal_analytics": legal_analytics
        }
    
    def get_document_by_id(self, index: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific document by ID
        """
        try:
            result = self.es.es.get(index=index, id=doc_id)
            return result.get("_source")
        except Exception as e:
            logger.error(f"Error retrieving document {doc_id} from {index}: {str(e)}")
            return None
    
    def search_postgresql_rag(self, query: str, db: Session = None) -> List[Dict[str, Any]]:
        """
        Direct search in PostgreSQL RAG database
        """
        if db is None:
            db = next(get_rag_db())
        
        try:
            # Example query - would need to be adapted to actual schema
            sql = """
            SELECT 
                id, 
                title, 
                content, 
                document_type, 
                ts_rank_cd(search_vector, to_tsquery('russian', :query)) as rank
            FROM 
                documents 
            WHERE 
                search_vector @@ to_tsquery('russian', :query)
            ORDER BY 
                rank DESC
            LIMIT 10
            """
            
            # Convert free text query to PostgreSQL tsquery format
            processed_query = " & ".join(query.split())
            
            result = db.execute(sa.text(sql), {"query": processed_query})
            return [dict(row) for row in result]
            
        except Exception as e:
            logger.error(f"Error searching PostgreSQL RAG: {str(e)}")
            return []

# Create singleton instance
document_retriever = DocumentRetriever()