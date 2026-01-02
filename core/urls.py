from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView, TemplateView # Adicionado TemplateView
from django.contrib.auth import views as auth_views

# Importação das nossas Views Personalizadas de Senha
from core_rh.views import CustomPasswordResetView, CustomPasswordResetDoneView

urlpatterns = [
    # --- ROTAS PWA (Adicionado) ---
    # O Android procura estes ficheiros na raiz
    path('manifest.json', TemplateView.as_view(template_name='manifest.json', content_type='application/manifest+json'), name='manifest'),
    path('service-worker.js', TemplateView.as_view(template_name='service-worker.js', content_type='application/javascript'), name='service-worker'),
    path('offline/', TemplateView.as_view(template_name='offline.html'), name='offline'),

    # 1. REDIRECIONAMENTO
    re_path(r'^admin/$', RedirectView.as_view(url='/admin/core_rh/equipe/', permanent=False)),

    # 2. ADMIN DO DJANGO
    path('admin/', admin.site.urls),

    # 3. SEU APP RH
    path('', include('core_rh.urls')),

    # 4. RECUPERAÇÃO DE SENHA
    path('accounts/password_reset/', CustomPasswordResetView.as_view(), name='password_reset'),
    path('accounts/password_reset/done/', CustomPasswordResetDoneView.as_view(), name='password_reset_done'),

    # 5. ROTAS DE AUTENTICAÇÃO
    path('accounts/', include('django.contrib.auth.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)