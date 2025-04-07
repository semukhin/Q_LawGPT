import logging
from aiosmtplib import SMTP
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import settings

logger = logging.getLogger(__name__)

async def send_email(to_email: str, subject: str, body: str):
    """
    Отправляет email используя настройки из конфигурации
    """
    try:
        message = MIMEMultipart()
        message["From"] = settings.MAIL_FROM
        message["To"] = to_email
        message["Subject"] = subject
        
        message.attach(MIMEText(body, "plain"))
        
        # Подключаемся к SMTP серверу
        smtp = SMTP(
            hostname=settings.MAIL_SERVER,
            port=settings.MAIL_PORT,
            use_tls=settings.MAIL_STARTTLS,
            start_tls=settings.MAIL_STARTTLS
        )
        
        await smtp.connect()
        await smtp.login(settings.MAIL_USERNAME, settings.MAIL_PASSWORD)
        await smtp.send_message(message)
        await smtp.quit()
        
        logger.info(f"Email успешно отправлен на {to_email}")
    except Exception as e:
        logger.error(f"Ошибка при отправке email: {str(e)}")
        raise

async def send_verification_email(to_email: str, code: int):
    """
    Отправляет email с кодом подтверждения
    """
    subject = "Подтверждение регистрации в LawGPT"
    body = f"""
    Здравствуйте!
    
    Для подтверждения вашего email-адреса введите следующий код:
    
    {code}
    
    Если вы не регистрировались в LawGPT, просто проигнорируйте это письмо.
    
    С уважением,
    Команда LawGPT
    """
    
    await send_email(to_email, subject, body)

async def send_recovery_email(to_email: str, code: int):
    """
    Отправляет email с кодом для сброса пароля
    """
    subject = "Сброс пароля в LawGPT"
    body = f"""
    Здравствуйте!
    
    Для сброса пароля введите следующий код:
    
    {code}
    
    Если вы не запрашивали сброс пароля в LawGPT, просто проигнорируйте это письмо.
    
    С уважением,
    Команда LawGPT
    """
    
    await send_email(to_email, subject, body) 