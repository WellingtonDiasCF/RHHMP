from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from django.contrib.auth import views as auth_views

# Importação das nossas Views Personalizadas de Senha
from core_rh.views import CustomPasswordResetView, CustomPasswordResetDoneView

urlpatterns = [
    # 1. REDIRECIONAMENTO (O Pulo do Gato)
    # Ao acessar o domínio raiz ou /admin/, vai para a lista de equipes
    re_path(r'^admin/$', RedirectView.as_view(url='/admin/core_rh/equipe/', permanent=False)),

    # 2. ADMIN DO DJANGO
    path('admin/', admin.site.urls),

    # 3. SEU APP RH (Rotas principais)
    path('', include('core_rh.urls')),

    # 4. RECUPERAÇÃO DE SENHA CUSTOMIZADA (CPF)
    # Estas rotas DEVEM vir antes do include('django.contrib.auth.urls')
    
    # Passo 1: Digitar o CPF
    path('accounts/password_reset/', 
         CustomPasswordResetView.as_view(), 
         name='password_reset'),

    # Passo 2: Mensagem de E-mail Enviado (com máscara no e-mail)
    path('accounts/password_reset/done/', 
         CustomPasswordResetDoneView.as_view(), 
         name='password_reset_done'),

    # 5. ROTAS DE AUTENTICAÇÃO PADRÃO DO DJANGO
    # (Login, Logout, Confirmar nova senha, Sucesso)
    path('accounts/', include('django.contrib.auth.urls')),
]

# Configuração para servir arquivos de mídia (Uploads) em modo DEBUG
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)