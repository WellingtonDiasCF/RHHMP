from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    # --- TELA INICIAL ---
    path('', views.home, name='home'),

    # --- FOLHA DE PONTO (FUNCIONÁRIO) ---
    path('folha-ponto/', views.folha_ponto_view, name='folha_ponto'),
    path('salvar-ponto/', views.salvar_ponto_view, name='salvar_ponto'),
    path('folha-ponto/gerar-pdf/', views.gerar_pdf_ponto_view, name='gerar_pdf_ponto'),

    # --- ÁREA DO GESTOR ---
    path('equipe/', views.area_gestor_view, name='area_gestor'),
    path('equipe/assinar/<int:func_id>/<int:mes>/<int:ano>/', views.assinar_ponto_gestor, name='assinar_ponto_gestor'),
    path('equipe/historico/<int:func_id>/', views.historico_funcionario_view, name='historico_funcionario'),

    # --- ÁREA DO RH (DASHBOARD COMPLETO) ---
    path('rh/', views.rh_summary_view, name='rh_summary'),
    path('rh/folhas-ponto/<int:equipe_id>/', views.rh_team_detail_view, name='rh_team_detail'),
    path('rh/download-lote/<int:equipe_id>/', views.rh_batch_download_view, name='rh_batch_download'),
    path('rh/liberar-edicao/<int:func_id>/<int:mes>/<int:ano>/', views.rh_unlock_timesheet_view, name='rh_unlock_timesheet'),

    # --- INTEGRAÇÃO COM DJANGO ADMIN (AJAX) ---
    path('api/admin/gestor-partial/', views.admin_gestor_partial_view, name='admin_gestor_partial'),
    path('api/admin/ponto-html/<int:func_id>/', views.admin_ponto_partial_view, name='admin_ponto_partial'),
    path('api/admin/ferias-partial/', views.admin_ferias_partial_view, name='admin_ferias_partial'),
    path('api/admin/contracheque/partial/', views.admin_contracheque_partial, name='admin_contracheque_partial'),

    # --- MÓDULO DE FÉRIAS ---
    path('minhas-ferias/', views.minhas_ferias_view, name='minhas_ferias'),
    path('minhas-ferias/upload/<int:ferias_id>/', views.upload_ferias_view, name='upload_ferias'),
    path('ferias/gerar-aviso/<int:ferias_id>/', views.gerar_aviso_ferias_pdf, name='gerar_aviso_ferias_pdf'),
    
    # --- AUTENTICAÇÃO E SENHAS ---
    path('accounts/login/', auth_views.LoginView.as_view(), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('primeiro-acesso/', views.trocar_senha_obrigatoria, name='trocar_senha_obrigatoria'),

    # Recuperação de Senha
    path('password_reset/', views.CustomPasswordResetView.as_view(), name='password_reset'),
    path('password_reset/done/', views.CustomPasswordResetDoneView.as_view(), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),

    # --- CONTRACHEQUES (FUNCIONÁRIO) ---
    path('meus-contracheques/', views.meus_contracheques, name='meus_contracheques'),
    path('assinar-contracheque/<int:pk>/', views.assinar_contracheque_local, name='assinar_contracheque_local'),
    
    # --- GESTÃO DE CONTRACHEQUES (RH) ---
    path('gestao-contracheques/', views.gerenciar_contracheques, name='gerenciar_contracheques'),
    
    # NOVAS ROTAS ADICIONADAS PARA OS BOTÕES DE AÇÃO:
    path('rh/contracheque/upload/<int:func_id>/', views.upload_individual_contracheque, name='upload_individual_contracheque'),
    path('rh/contracheque/excluir/<int:cc_id>/', views.excluir_contracheque, name='excluir_contracheque'),
    path('meus-atestados/', views.meus_atestados_view, name='meus_atestados'),
    # ...
    path('api/admin/atestados-partial/', views.admin_atestados_partial_view, name='admin_atestados_partial'),
    path('rh/atestado/acao/', views.rh_acao_atestado, name='rh_acao_atestado'),
]