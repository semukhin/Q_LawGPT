from typing import Dict, Any, List, Optional
import logging
import aiohttp
import json
import asyncio
from app.core.config import settings
from app.services.ai_service import call_qwen_api
from app.services.elasticsearch_service import elasticsearch_service

logger = logging.getLogger(__name__)

class DocumentPrepAgent:
    """
    Agent specialized in document preparation (lawsuits, appeals, contracts)
    """
    
    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self.model = "qwen/qwen2.5-vl-72b-instruct:free"
        self.es_service = elasticsearch_service
    
    async def analyze_document_type(self, query: str) -> Dict[str, Any]:
        """
        Analyze the query to determine the type of document needed
        """
        system_prompt = """
        Вы - специализированный юридический агент по подготовке процессуальных документов и договоров.
        Ваша задача - проанализировать запрос пользователя и определить:
        
        1. Тип документа, который требуется подготовить
        2. Ключевые параметры, необходимые для подготовки документа
        3. Какие дополнительные данные нужны от пользователя
        
        Ответьте в формате JSON:
        {
            "document_type": "тип документа (исковое_заявление, апелляционная_жалоба, договор и т.д.)",
            "parameters": {"параметр1": "значение", "параметр2": "значение"},
            "missing_data": ["данные1", "данные2"]
        }
        """
        
        user_message = f"Запрос пользователя: {query}\n\nОпределите тип документа и необходимые параметры."
        
        try:
            result = call_qwen_api(
                prompt=user_message,
                system_message=system_prompt,
                api_key=self.api_key,
                max_tokens=4000,
                temperature=0.7
            )
            
            if not result["success"]:
                logger.error(f"Error calling Qwen API: {result.get('error', 'Unknown error')}")
                return {"error": f"API Error: {result.get('error', 'Unknown error')}"}
            
            content = result["text"]
            
            # Extract JSON from the response
            try:
                json_start = content.find("{")
                json_end = content.rfind("}") + 1
                json_str = content[json_start:json_end]
                analysis = json.loads(json_str)
                return analysis
            except json.JSONDecodeError:
                logger.error(f"Error parsing JSON from response: {content}")
                # Fallback to default analysis
                return {
                    "document_type": "unknown",
                    "parameters": {},
                    "missing_data": ["Уточните тип документа", "Укажите основные параметры"]
                }
        except Exception as e:
            logger.error(f"Error in document prep agent analysis: {str(e)}")
            return {"error": str(e)}
    
    async def generate_document(self, query: str, document_type: str, parameters: Dict[str, Any]) -> str:
        """
        Generate a legal document based on parameters
        """
        # Get templates and reference materials using ElasticsearchService
        legal_norms = self.es_service.search_law_chunks(query, top_n=5)
        court_decisions = self.es_service.search_law_chunks(query, top_n=3)
        
        system_prompt = f"""
        Вы - специализированный юридический агент по подготовке процессуальных документов и договоров.
        Ваша задача - подготовить документ типа "{document_type}" на основе запроса пользователя
        и предоставленных параметров.
        
        Документ должен:
        1. Соответствовать всем требованиям российского законодательства
        2. Содержать все необходимые реквизиты и разделы
        3. Использовать корректную юридическую терминологию
        4. Быть хорошо структурированным и готовым к использованию
        
        Создайте полностью оформленный документ.
        """
        
        # Prepare context with laws and court decisions
        context = "Релевантные правовые нормы и судебная практика:\n\n"
        
        if legal_norms:
            context += "Правовые нормы:\n"
            for i, law in enumerate(legal_norms):
                context += f"{i+1}. {law}\n\n"
        
        if court_decisions:
            context += "Судебная практика:\n"
            for i, decision in enumerate(court_decisions):
                context += f"{i+1}. {decision}\n\n"
        
        # Convert parameters to string
        params_str = "\n".join([f"{k}: {v}" for k, v in parameters.items()])
        
        user_message = f"""
        Запрос пользователя: {query}
        
        Тип документа: {document_type}
        
        Параметры:
        {params_str}
        
        {context}
        
        Пожалуйста, подготовьте полностью оформленный документ.
        """
        
        try:
            result = call_qwen_api(
                prompt=user_message,
                system_message=system_prompt,
                api_key=self.api_key,
                max_tokens=4000,
                temperature=0.7
            )
            
            if not result["success"]:
                logger.error(f"Error calling Qwen API: {result.get('error', 'Unknown error')}")
                return f"Произошла ошибка при генерации документа: {result.get('error', 'Unknown error')}"
            
            content = result["text"]
            return content
        except Exception as e:
            logger.error(f"Error in document generation: {str(e)}")
            return f"Произошла ошибка при генерации документа: {str(e)}"
    
    async def process_query(self, query: str, additional_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Process the query and generate a legal document
        """
        try:
            # Analyze document type and required parameters
            document_analysis = await self.analyze_document_type(query)
            
            if "error" in document_analysis:
                return document_analysis
            
            document_type = document_analysis.get("document_type", "unknown")
            parameters = document_analysis.get("parameters", {})
            missing_data = document_analysis.get("missing_data", [])
            
            # Add additional data if provided
            if additional_data:
                parameters.update(additional_data)
            
            # Check if we have all required data
            if missing_data and not additional_data:
                return {
                    "document_type": document_type,
                    "parameters": parameters,
                    "missing_data": missing_data,
                    "status": "need_more_info"
                }
            
            # Generate the document
            document = await self.generate_document(query, document_type, parameters)
            
            return {
                "document_type": document_type,
                "document": document,
                "parameters": parameters
            }
        except Exception as e:
            logger.error(f"Error processing query in document prep agent: {str(e)}")
            return {"error": str(e)}

# Create singleton instance
document_prep_agent = DocumentPrepAgent()