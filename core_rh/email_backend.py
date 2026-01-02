# core_rh/email_backend.py
import ssl
from django.core.mail.backends.smtp import EmailBackend

class EmailBackendSemVerificacao(EmailBackend):
    """
    Backend de e-mail personalizado que ignora erros de verificação SSL 
    (Hostname mismatch ou certificado auto-assinado).
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Cria um contexto SSL que não verifica o nome do host
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE