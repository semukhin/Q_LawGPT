from typing import List, Dict, Any, Optional
import logging
import json
import asyncio
from app.core.config import settings
from app.services.web_search import web_search_service
from app.services.ai_service import call_qwen_api
from app.services.elasticsearch_service import elasticsearch_service
from app.agents.legal_norms import legal_norms_agent
from app.agents.judicial import judicial_practice_agent
from app.agents.analytics import analytics_agent
from app.agents.document_prep import document_prep_agent
from app.agents.document_analysis import document_analysis_agent

logger = logging.getLogger(__name__)

class CoordinatorAgent:
    """
    Coordinator Agent responsible for orchestrating the workflow
    of other specialist agents
    """
    
    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self.model = "qwen/qwen2.5-vl-72b-instruct:free"  # Use the most capable model for coordination
        self.es_service = elasticsearch_service
    
    
    async def analyze_query(self, query: str, has_image: bool = False) -> Dict[str, Any]:
        """
        Анализирует запрос пользователя и определяет, каких агентов следует привлечь
        """
        # Поиск базовой релевантной информации
        try:
            legal_info = await self.es_service.search_law_chunks(query, top_n=5)
            
            system_prompt = """
            Вы - координатор системы из специализированных юридических агентов. Ваша задача - проанализировать
            запрос пользователя и определить, какие агенты должны быть вовлечены в подготовку ответа и в каком порядке.
            
            Доступные агенты:
            1. legal_norms_agent - Специалист по правовым нормам (законы, постановления, кодексы)
            2. judicial_practice_agent - Специалист по судебной практике (решения судов, обзоры практики)
            3. analytics_agent - Специалист по аналитике (комментарии, статьи, книги)
            4. document_prep_agent - Специалист по подготовке документов (иски, жалобы, договоры)
            5. document_analysis_agent - Специалист по анализу изображений документов
            
            Проанализируйте запрос пользователя и определите:
            1. Какие агенты должны быть вовлечены (не всегда нужны все)
            2. В каком порядке они должны работать
            3. Какие уточняющие вопросы следует задать пользователю
            
            Ответьте в формате JSON:
            {
                "agents": ["agent1", "agent2"],
                "clarifying_questions": ["Вопрос 1?", "Вопрос 2?"],
                "plan": "Краткое описание плана подготовки ответа",
                "confidence": 0.95
            }
            """
            
            # Если есть изображение, добавляем агент анализа документов
            if has_image:
                agents = ["document_analysis_agent"]
                # Если это только изображение без текста запроса, используем только анализ документов
                if not query or query.strip() == "":
                    return {
                        "agents": agents,
                        "clarifying_questions": ["Какой аспект документа вас интересует?"],
                        "plan": "Анализ изображения документа",
                        "reasoning": "Пользователь предоставил только изображение без текстового запроса. Начну с анализа документа на изображении."
                    }

            # Формируем сообщение с учетом найденной правовой информации
            user_message = f"Запрос пользователя: {query}\n\n"
            if legal_info:
                user_message += "Найдена следующая релевантная правовая информация:\n"
                for i, info in enumerate(legal_info, 1):
                    user_message += f"{i}. {info}\n\n"
            user_message += "Проанализируйте запрос и определите агентов и вопросы."
            
            result = await call_qwen_api(
                prompt=user_message,
                system_message=system_prompt,
                api_key=self.api_key,
                max_tokens=2000,
                temperature=0.7
            )
            
            if not result["success"]:
                return {"error": f"API Error: {result.get('error', 'Unknown error')}"}
            
            content = result["text"]
            
            # Извлекаем JSON из ответа
            try:
                json_start = content.find("{")
                json_end = content.rfind("}") + 1
                json_str = content[json_start:json_end]
                analysis = json.loads(json_str)
                
                # Добавляем информацию о рассуждении
                analysis["reasoning"] = f"На основе запроса и правовой информации были определены следующие агенты: {', '.join(analysis['agents'])}. План действий: {analysis['plan']}"
                
                return analysis
            except Exception as e:
                # Запасной вариант, если не удалось распарсить JSON
                default_agents = ["legal_norms_agent", "judicial_practice_agent", "analytics_agent"]
                return {
                    "agents": default_agents,
                    "clarifying_questions": ["Уточните, какие аспекты вопроса наиболее важны?"],
                    "plan": "Анализ правовых норм, изучение судебной практики, сбор аналитики",
                    "reasoning": f"Не удалось определить оптимальных агентов автоматически. Используются стандартные агенты: {', '.join(default_agents)}"
                }
        except Exception as e:
            return {
                "error": str(e),
                "agents": ["legal_norms_agent"],
                "reasoning": f"Произошла ошибка: {str(e)}. Используется базовый агент правовых норм."
            }

    async def delegate_to_agents(self, query: str, agent_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Делегирует запрос определенным агентам и собирает их ответы
        """
        results = {}
        if "error" in agent_analysis:
            return {"error": agent_analysis["error"]}
        
        # Получаем список агентов для запуска
        agents_to_run = agent_analysis.get("agents", [])
        
        # Запускаем всех агентов параллельно
        tasks = []
        
        for agent_name in agents_to_run:
            if agent_name == "legal_norms_agent":
                tasks.append((agent_name, legal_norms_agent.process_query(query)))
            elif agent_name == "judicial_practice_agent":
                tasks.append((agent_name, judicial_practice_agent.process_query(query)))
            elif agent_name == "analytics_agent":
                tasks.append((agent_name, analytics_agent.process_query(query)))
            elif agent_name == "document_prep_agent":
                tasks.append((agent_name, document_prep_agent.process_query(query)))
            elif agent_name == "document_analysis_agent":
                tasks.append((agent_name, document_analysis_agent.process_query(query)))
        
        # Собираем результаты всех агентов
        for agent_name, task in tasks:
            try:
                result = await task
                results[agent_name] = result
            except Exception as e:
                results[agent_name] = {"error": str(e)}
        
        return results

    async def synthesize_response(self, query: str, agent_responses: Dict[str, Any], 
                            agent_analysis: Dict[str, Any] = None) -> Dict[str, str]:
        """
        Синтезирует финальный ответ на основе результатов работы всех агентов
        Возвращает как полный ответ, так и рассуждения для отображения в UI
        """
        # Собираем данные из результатов агентов
        combined_info = {}
        reasoning_steps = []
        
        # Добавляем рассуждения координатора (если есть)
        if agent_analysis and "reasoning" in agent_analysis:
            reasoning_steps.append(f"🔍 Координатор: {agent_analysis['reasoning']}")
        
        # Обрабатываем ответы каждого агента
        for agent_name, response in agent_responses.items():
            if "error" in response:
                reasoning_steps.append(f"❌ {agent_name}: {response['error']}")
                continue
                
            reasoning_steps.append(f"✅ {agent_name}: Собраны данные")
            
            # Обрабатываем данные от разных агентов
            if agent_name == "legal_norms_agent":
                combined_info["legal_norms"] = response.get("legal_norms", [])
                combined_info["legal_analysis"] = response.get("analysis", "")
            elif agent_name == "judicial_practice_agent":
                combined_info["court_decisions"] = response.get("court_decisions", [])
                combined_info["judicial_analysis"] = response.get("analysis", {})
            elif agent_name == "analytics_agent":
                combined_info["analytics"] = response.get("analytics_results", [])
                combined_info["analytics_analysis"] = response.get("analysis", "")
            elif agent_name == "document_prep_agent":
                combined_info["document"] = response.get("document", "")
                combined_info["document_type"] = response.get("document_type", "")
            elif agent_name == "document_analysis_agent":
                combined_info["document_analysis"] = response.get("document_analysis", "")
                combined_info["document_type"] = response.get("document_type", "")
        
        reasoning_steps.append("🔄 Синтез финального ответа на основе всех данных...")
        
        # Формируем промпт для финального ответа
        system_prompt = """
        Вы - опытный юридический ассистент, специализирующийся на российском законодательстве.
        Ваша задача - синтезировать полный, точный и хорошо структурированный ответ на основе
        данных, собранных специализированными юридическими агентами.
        
        Ваш ответ должен:
        1. Быть юридически точным и основанным на предоставленных данных
        2. Содержать релевантные ссылки на законодательство и судебную практику
        3. Быть хорошо структурированным, с заголовками и подзаголовками где это уместно
        4. Включать конкретные рекомендации, если это возможно
        5. Быть написанным понятным языком с объяснением сложных юридических терминов
        
        Сфокусируйтесь на самой релевантной информации и не повторяйтесь.
        """
        
        user_message = f"Запрос пользователя: {query}\n\n"
        user_message += f"Собранная информация:\n{json.dumps(combined_info, ensure_ascii=False, indent=2)}\n\n"
        user_message += "Пожалуйста, синтезируйте полный ответ на запрос пользователя, опираясь на все собранные данные."
        
        # Вызываем API для финального ответа
        result = await call_qwen_api(
            prompt=user_message,
            system_message=system_prompt,
            api_key=self.api_key,
            max_tokens=4000,
            temperature=0.7
        )
        
        if not result["success"]:
            error_msg = f"Произошла ошибка при синтезе ответа: {result.get('error', 'неизвестная ошибка')}"
            reasoning_steps.append(f"❌ Ошибка синтеза: {error_msg}")
            return {
                "answer": error_msg,
                "reasoning": "\n".join(reasoning_steps)
            }
        
        reasoning_steps.append("✅ Финальный ответ сформирован")
        
        return {
            "answer": result["text"],
            "reasoning": "\n".join(reasoning_steps)
        }

    async def process_query_with_stream(self, query: str, websocket_conn = None) -> Dict[str, Any]:
        """
        Обрабатывает запрос с потоковой передачей информации о ходе выполнения через WebSocket
        """
        # Определяем, какие агенты нужны
        if websocket_conn:
            await websocket_conn.send_json({
                "type": "thinking",
                "content": "Анализирую запрос и определяю необходимых агентов..."
            })
        
        agent_analysis = await self.analyze_query(query)
        
        if "error" in agent_analysis:
            if websocket_conn:
                await websocket_conn.send_json({
                    "type": "error",
                    "content": f"Ошибка анализа запроса: {agent_analysis['error']}"
                })
            return {"error": agent_analysis["error"]}
        
        # Отправляем результаты анализа через WebSocket
        if websocket_conn:
            await websocket_conn.send_json({
                "type": "thinking",
                "content": f"План: {agent_analysis.get('plan', 'План не определен')}\n" +
                        f"Выбранные агенты: {', '.join(agent_analysis.get('agents', []))}"
            })
        
        # Запускаем агентов
        if websocket_conn:
            await websocket_conn.send_json({
                "type": "thinking",
                "content": "Запускаю выбранных агентов для сбора данных..."
            })
        
        agent_responses = await self.delegate_to_agents(query, agent_analysis)
        
        # Синтезируем финальный ответ
        if websocket_conn:
            await websocket_conn.send_json({
                "type": "thinking",
                "content": "Синтезирую финальный ответ на основе всех данных..."
            })
        
        result = await self.synthesize_response(query, agent_responses, agent_analysis)
        
        # Отправляем финальный ответ
        if websocket_conn:
            await websocket_conn.send_json({
                "type": "answer",
                "content": result["answer"],
                "reasoning": result["reasoning"]
            })
        
        return result



    async def gather_web_info(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """
        Собирает информацию из веб-источников для обогащения контекста
        """
        try:
            # Поиск и скрейпинг статей
            articles = await web_search_service.search_and_scrape(query, max_results)
            
            # Формируем контекст из найденных статей
            context = {
                "web_sources": [],
                "summary": ""
            }
            
            for article in articles:
                context["web_sources"].append({
                    "title": article["title"],
                    "url": article["url"],
                    "content": article["content"][:1000]  # Ограничиваем длину для экономии токенов
                })
            
            # Формируем краткое описание найденных источников
            if context["web_sources"]:
                sources_summary = "\n".join([
                    f"- {source['title']} ({source['url']})"
                    for source in context["web_sources"]
                ])
                context["summary"] = f"Найдены следующие релевантные источники:\n{sources_summary}"
            
            return context
            
        except Exception as e:
            logger.error(f"Ошибка при сборе веб-информации: {str(e)}")
            return {"web_sources": [], "summary": "Не удалось собрать информацию из веб-источников"}

# Create singleton instance
coordinator_agent = CoordinatorAgent()