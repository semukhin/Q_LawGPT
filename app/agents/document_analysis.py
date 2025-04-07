from typing import Dict, Any, List, Optional, Union
import logging
import asyncio
import base64
import os
from app.core.config import settings
from app.services.ai_service import call_qwen_api
from app.services.elasticsearch_service import elasticsearch_service

logger = logging.getLogger(__name__)

class DocumentAnalysisAgent:
    """
    Агент для анализа юридических документов на изображениях
    
    Функции:
    - Анализ документов из изображений
    - Определение типа документа
    - Извлечение ключевой юридической информации
    - Сохранение результатов анализа в Elasticsearch
    """
    
    def __init__(self):
        """
        Инициализация агента анализа документов
        """
        self.site_url = settings.BASE_URL
        self.site_name = "LawGPT.ru"
        self.es_service = elasticsearch_service
        
        # Типы документов и их ключевые признаки
        self.document_types = {
            "contract": ["договор", "соглашение", "контракт", "сторона", "обязуется"],
            "lawsuit": ["исковое заявление", "иск", "истец", "ответчик", "суд", "требование"],
            "court_decision": ["решение суда", "постановление", "определение суда", "приговор"],
            "appeal": ["апелляционная жалоба", "апелляция", "жалоба", "обжалование"],
            "power_of_attorney": ["доверенность", "уполномочивает", "доверяет", "поручает"],
            "statute": ["устав", "положение", "учредительный документ"],
            "legal_statement": ["заявление", "ходатайство"],
            "notary_document": ["нотариальный", "нотариус", "удостоверено"],
            "official_letter": ["официальное письмо", "уведомление", "извещение"]
        }
    
    async def analyze_document_image(self, image_url: str) -> Dict[str, Any]:
        """
        Анализирует изображение юридического документа
        
        Аргументы:
        image_url -- URL изображения или путь к локальному файлу
        
        Возвращает:
        Словарь с результатами анализа документа
        """
        prompt = """
        Проанализируй этот юридический документ и выдели следующую информацию:
        1. Тип документа (договор, судебное решение, заявление и т.д.)
        2. Основные стороны и их реквизиты (ФИО, организации, адреса, реквизиты)
        3. Ключевые положения и обязательства сторон
        4. Даты, сроки и временные рамки действия документа
        5. Юридически значимые детали (условия, размеры платежей, санкции)
        6. Основания возникновения правоотношений
        
        Предоставь структурированный ответ на русском языке с чётким разделением на разделы.
        Если какая-то информация отсутствует или нечитаема, укажи это.
        """
        
        # Проверяем, является ли image_url локальным файлом
        if os.path.isfile(image_url):
            # Если это локальный файл, конвертируем его в base64
            try:
                with open(image_url, "rb") as img_file:
                    base64_image = base64.b64encode(img_file.read()).decode('utf-8')
                    image_url = f"data:image/jpeg;base64,{base64_image}"
                    logger.info(f"Локальный файл конвертирован в base64")
            except Exception as e:
                logger.error(f"Ошибка при чтении локального файла: {str(e)}")
                return {
                    "error": f"Не удалось прочитать файл: {str(e)}",
                    "success": False
                }
        
        # Вызов API с передачей изображения
        result = await call_qwen_api(
            prompt=prompt,
            image_url=image_url,
            max_tokens=3000,  # Увеличиваем для более полного анализа
            temperature=0.3   # Низкая температура для точности
        )
        
        if result["success"]:
            document_type = self._determine_document_type(result["text"])
            
            # Добавляем типизированные подсказки для дальнейшего анализа
            follow_up_tips = self._generate_follow_up_tips(document_type)
            
            analysis_result = {
                "document_analysis": result["text"],
                "document_type": document_type,
                "document_type_readable": self._get_readable_document_type(document_type),
                "follow_up_tips": follow_up_tips,
                "success": True
            }
            
            # Сохраняем результат анализа в Elasticsearch
            try:
                await self._save_analysis_to_elasticsearch(analysis_result)
            except Exception as e:
                logger.error(f"Ошибка при сохранении анализа в Elasticsearch: {str(e)}")
            
            return analysis_result
        else:
            error_msg = result.get('error', 'Неизвестная ошибка')
            logger.error(f"Ошибка анализа документа: {error_msg}")
            return {
                "error": f"Не удалось проанализировать документ: {error_msg}",
                "success": False
            }
    
    async def _save_analysis_to_elasticsearch(self, analysis_result: Dict[str, Any]) -> None:
        """
        Сохраняет результат анализа документа в Elasticsearch
        
        Аргументы:
        analysis_result -- словарь с результатами анализа
        """
        try:
            document_data = {
                "content": analysis_result["document_analysis"],
                "document_type": analysis_result["document_type"],
                "document_type_readable": analysis_result["document_type_readable"],
                "analysis_date": "now",
                "source": "document_analysis",
                "metadata": {
                    "follow_up_tips": analysis_result["follow_up_tips"]
                }
            }
            
            # Используем ElasticsearchService для сохранения документа
            await self.es_service.index_document(
                index="document_analysis",
                document=document_data
            )
            
            logger.info("Результат анализа успешно сохранен в Elasticsearch")
        except Exception as e:
            logger.error(f"Ошибка при сохранении в Elasticsearch: {str(e)}")
            raise
    
    def _determine_document_type(self, text: str) -> str:
        """
        Определяет тип документа на основе анализа содержания
        
        Аргументы:
        text -- текст анализа документа
        
        Возвращает:
        Строковый код типа документа
        """
        if not text:
            return "unknown"
        
        text = text.lower()
        scores = {}
        
        # Подсчитываем "очки" для каждого типа документа
        for doc_type, keywords in self.document_types.items():
            score = 0
            for keyword in keywords:
                if keyword in text:
                    score += 1
            scores[doc_type] = score
        
        # Находим тип с максимальным количеством совпадений
        if not scores:
            return "unknown"
        
        max_score = max(scores.values())
        if max_score == 0:
            return "other_legal_document"
        
        # Если есть несколько типов с одинаковым количеством совпадений, выбираем первый
        for doc_type, score in scores.items():
            if score == max_score:
                return doc_type
        
        return "other_legal_document"
    
    def _get_readable_document_type(self, doc_type: str) -> str:
        """
        Возвращает читаемое название типа документа на русском
        """
        readable_types = {
            "contract": "Договор",
            "lawsuit": "Исковое заявление",
            "court_decision": "Судебное решение",
            "appeal": "Апелляционная жалоба",
            "power_of_attorney": "Доверенность",
            "statute": "Устав",
            "legal_statement": "Ходатайство",
            "notary_document": "Нотариальный документ",
            "official_letter": "Официальное письмо",
            "other_legal_document": "Иной юридический документ",
            "unknown": "Неопределенный тип документа"
        }
        return readable_types.get(doc_type, "Неопределенный тип документа")
    
    def _generate_follow_up_tips(self, doc_type: str) -> List[str]:
        """
        Генерирует подсказки для дальнейших действий в зависимости от типа документа
        """
        tips = {
            "contract": [
                "Проверьте сроки исполнения обязательств",
                "Обратите внимание на условия расторжения договора",
                "Проверьте ответственность сторон за нарушение обязательств"
            ],
            "lawsuit": [
                "Проверьте соблюдение процессуальных сроков",
                "Обратите внимание на обоснованность исковых требований",
                "Рассмотрите возможность мирового соглашения"
            ],
            "court_decision": [
                "Проверьте сроки обжалования решения",
                "Изучите мотивировочную часть решения",
                "Определите порядок исполнения решения"
            ],
            "appeal": [
                "Проверьте соблюдение сроков подачи жалобы",
                "Изучите обоснованность доводов жалобы",
                "Рассмотрите необходимость предоставления дополнительных доказательств"
            ],
            "power_of_attorney": [
                "Проверьте срок действия доверенности",
                "Уточните объем полномочий представителя",
                "Проверьте наличие права передоверия"
            ]
        }
        
        # Возвращаем подсказки для данного типа документа или общие подсказки
        return tips.get(doc_type, [
            "Проверьте правильность оформления документа",
            "Обратите внимание на сроки и даты в документе",
            "Изучите права и обязанности сторон"
        ])
    
    async def advanced_document_analysis(self, image_url: str, specific_question: str = None) -> Dict[str, Any]:
        """
        Проводит углубленный анализ документа с возможностью задать конкретный вопрос
        
        Аргументы:
        image_url -- URL изображения или путь к локальному файлу
        specific_question -- конкретный вопрос по документу (опционально)
        
        Возвращает:
        Словарь с результатами углубленного анализа
        """
        # Сначала получаем базовый анализ
        base_analysis = await self.analyze_document_image(image_url)
        
        if not base_analysis.get("success", False):
            return base_analysis
        
        # Если указан конкретный вопрос, запрашиваем дополнительный анализ
        if specific_question:
            prompt = f"""
            Вам представлен анализ юридического документа:
            
            {base_analysis['document_analysis']}
            
            Пожалуйста, ответьте на следующий конкретный вопрос о документе:
            {specific_question}
            
            Дайте детальный ответ на основе информации из документа. Если в документе недостаточно данных для ответа, 
            укажите это и предложите, какую дополнительную информацию нужно запросить.
            """
            
            specific_result = await call_qwen_api(
                prompt=prompt,
                max_tokens=1500,
                temperature=0.3
            )
            
            if specific_result["success"]:
                base_analysis["specific_analysis"] = specific_result["text"]
            else:
                base_analysis["specific_analysis_error"] = specific_result.get("error", "Не удалось выполнить анализ по конкретному вопросу")
        
        return base_analysis
    
    async def process_query(self, query_data: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Обрабатывает запрос с изображением и опционально текстом
        
        Аргументы:
        query_data -- URL изображения или словарь с параметрами {image_url, question}
        
        Возвращает:
        Результат анализа документа
        """
        try:
            # Проверяем тип входных данных
            if isinstance(query_data, str):
                # Если передана только строка, считаем её URL изображения
                return await self.analyze_document_image(query_data)
            elif isinstance(query_data, dict) and 'image_url' in query_data:
                # Если передан словарь с параметрами
                image_url = query_data['image_url']
                specific_question = query_data.get('question')
                
                if specific_question:
                    # Если есть конкретный вопрос, делаем расширенный анализ
                    return await self.advanced_document_analysis(image_url, specific_question)
                else:
                    # Иначе делаем обычный анализ
                    return await self.analyze_document_image(image_url)
            else:
                return {
                    "error": "Неверный формат запроса. Ожидается URL изображения или словарь с параметрами",
                    "success": False
                }
                
        except Exception as e:
            logger.error(f"Ошибка обработки запроса в агенте анализа документов: {str(e)}")
            return {"error": str(e), "success": False}

# Создание экземпляра-синглтона
document_analysis_agent = DocumentAnalysisAgent()
