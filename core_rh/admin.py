import json
import io
from django.contrib import admin
from django.contrib.auth.models import User, Group
from django.utils.html import format_html
from django.utils.safestring import mark_safe 
from django import forms
from django.urls import reverse, path
from django.shortcuts import redirect, render
from django.contrib import messages
from django.core.files.base import ContentFile
import pdfplumber
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4


from .models import (
    Funcionario, RegistroPonto, Cargo, Equipe, 
    Ferias, Contracheque, Atestado, ControleKM, TrechoKM, DespesaDiversa
)
from .forms import UploadLoteContrachequeForm

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    PdfReader = None
    PdfWriter = None

# --- PERMISSÕES PERSONALIZADAS (RH) ---

def is_rh_member(user):
    # Retorna True se o usuário é Superuser ou membro da Equipe RH
    if not user or not user.is_authenticated: return False
    if user.is_superuser: return True
    
    if user.groups.filter(name='RH').exists(): return True

    try:
        if hasattr(user, 'funcionario'):
            func = user.funcionario
            rh_names = ['RH', 'Recursos Humanos', 'Gestão de Pessoas']
            
            if func.equipe and func.equipe.nome in rh_names: return True
            
            if func.outras_equipes.filter(nome__in=rh_names).exists(): return True
    except Exception:
        pass
        
    return False

class RHAccessMixin:
    def has_module_permission(self, request):
        return is_rh_member(request.user) or super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        return is_rh_member(request.user) or super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        return is_rh_member(request.user) or super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return is_rh_member(request.user) or super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return is_rh_member(request.user) or super().has_delete_permission(request, obj)


# --- FORMULÁRIO PERSONALIZADO ---
class FuncionarioAdminForm(forms.ModelForm):
    username = forms.CharField(label="Usuário (Login/CPF)", required=True)
    email = forms.EmailField(label="E-mail", required=True)
    password = forms.CharField(label="Senha", widget=forms.PasswordInput, required=False, help_text="Deixe vazio para manter a senha atual.")
    is_active = forms.BooleanField(label="Acesso Ativo?", required=False, initial=True)

    class Meta:
        model = Funcionario
        fields = '__all__'
        exclude = ('usuario',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if 'equipe' in self.fields:
            self.fields['equipe'].queryset = Equipe.objects.filter(oculta=False)
            
        if 'outras_equipes' in self.fields:
            self.fields['outras_equipes'].queryset = Equipe.objects.all()

        if self.instance and self.instance.pk and self.instance.usuario:
            self.fields['username'].initial = self.instance.usuario.username
            self.fields['email'].initial = self.instance.usuario.email
            self.fields['is_active'].initial = self.instance.usuario.is_active


# --- ADMINS ---

@admin.register(Funcionario)
class FuncionarioAdmin(RHAccessMixin, admin.ModelAdmin):
    form = FuncionarioAdminForm
    list_display = ('nome_completo', 'cargo', 'equipe', 'get_local_trabalho')
    list_filter = ('local_trabalho_estado', 'equipe', 'cargo') 
    search_fields = ('nome_completo', 'cpf', 'usuario__username', 'email')
    filter_horizontal = ('outras_equipes',)
    
    class Media:
        js = ('js/cep_admin.js', 'js/admin_realtime_search.js',)

    fieldsets = (
        ('🔐 Acesso', {'fields': ('username', 'password', 'email', 'is_active', 'primeiro_acesso')}),
        ('👤 Dados Pessoais', {'fields': ('nome_completo', 'cpf', 'data_admissao')}),
        ('📄 Documentação (Para Férias)', {'fields': (('matricula', 'registro_geral'), ('carteira_trabalho', 'serie_ctps'))}),
        ('📍 Endereço', {'fields': ('cep', 'endereco', 'bairro', 'cidade', 'estado', 'local_trabalho_estado')}),
        ('🏢 Corporativo', {'fields': ('cargo', 'equipe', 'outras_equipes', 'numero_contrato')}),
        ('⏰ Ponto', {'fields': ('jornada_entrada', 'jornada_saida', 'intervalo_padrao')}),
    )

    def get_local_trabalho(self, obj):
        if obj.equipe:
            return obj.equipe.local_trabalho
        return "-" 
    
    get_local_trabalho.short_description = 'Local de Trabalho'

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        estados = Funcionario.objects.exclude(local_trabalho_estado__isnull=True).exclude(local_trabalho_estado='').values_list('local_trabalho_estado', flat=True).distinct().order_by('local_trabalho_estado')
        mapa_estado_equipe = {}
        for est in estados:
            ids = Funcionario.objects.filter(local_trabalho_estado=est).exclude(equipe__isnull=True).values_list('equipe_id', flat=True).distinct()
            mapa_estado_equipe[est] = list(ids)
        todas_equipes = list(Equipe.objects.values('id', 'nome').order_by('nome'))
        extra_context['filter_estados'] = list(estados)
        extra_context['filter_equipes'] = todas_equipes
        extra_context['json_mapa_equipes'] = json.dumps(mapa_estado_equipe)
        if is_rh_member(request.user):
            extra_context['total_atestados_pendentes'] = Atestado.objects.filter(status='Pendente').count()
        return super().changelist_view(request, extra_context=extra_context)

    def save_model(self, request, obj, form, change):
        username = form.cleaned_data['username']
        email = form.cleaned_data['email']
        password = form.cleaned_data['password']
        is_active = form.cleaned_data['is_active']
        
        if obj.nome_completo:
            nomes = obj.nome_completo.strip().split()
            first_name = nomes[0].title()
            last_name = ' '.join(nomes[1:]).title() if len(nomes) > 1 else ''
        else:
            first_name = 'Usuario'
            last_name = 'Novo'

        if change and obj.usuario:
            user = obj.usuario
            user.username = username
            user.email = email
            user.first_name = first_name
            user.last_name = last_name
            user.is_active = is_active
            if password:
                user.set_password(password)
            user.save()
            obj.save()
        else:
            try:
                user = User.objects.create_user(username=username, email=email, password=password or '123456', first_name=first_name, last_name=last_name)
                user.is_active = is_active
                user.save()
                obj.usuario = user
                if not password:
                    obj.primeiro_acesso = True
                obj.save()
            except Exception as e:
                if User.objects.filter(username=username).exists():
                     obj.usuario = User.objects.get(username=username)
                     obj.save()

@admin.register(Equipe)
class EquipeAdmin(RHAccessMixin, admin.ModelAdmin):
    list_display = ('nome', 'local_trabalho', 'listar_gestores', 'oculta')
    search_fields = ('nome', 'local_trabalho')
    list_filter = ('local_trabalho', 'oculta') 
    filter_horizontal = ('gestores',)
    
    class Media:
        js = ('js/admin_realtime_search.js',)
    
    fields = ('nome', 'local_trabalho', 'gestor', 'gestores', 'oculta')

    def listar_gestores(self, obj):
        return ", ".join([g.nome_completo.split()[0] for g in obj.gestores.all()])
    listar_gestores.short_description = "Gestores"

@admin.register(Cargo)
class CargoAdmin(RHAccessMixin, admin.ModelAdmin):
    pass

@admin.register(RegistroPonto)
class RegistroPontoAdmin(RHAccessMixin, admin.ModelAdmin):
    # Adicionamos 'botao_pdf' na lista de exibição
    list_display = ('funcionario', 'data', 'entrada_manha', 'saida_tarde', 'status_assinaturas', 'botao_pdf')
    list_filter = ('data', 'funcionario__equipe', 'assinado_funcionario', 'assinado_gestor')
    search_fields = ('funcionario__nome_completo',)
    date_hierarchy = 'data'

    def status_assinaturas(self, obj):
        func = "✅" if obj.assinado_funcionario else "❌"
        gest = "✅" if obj.assinado_gestor else "❌"
        return format_html("Func: {} | Gest: {}", func, gest)
    status_assinaturas.short_description = "Assinaturas"

    # --- NOVO CÓDIGO: CRIA O BOTÃO DE DOWNLOAD ---
    def botao_pdf(self, obj):
        try:
            # Tenta gerar o link. É necessário que exista uma URL nomeada 'gerar_pdf_ponto'
            # apontando para a view gerar_pdf_ponto_view no seu urls.py
            url = reverse('gerar_pdf_ponto') 
            
            # Monta o link com os parâmetros que sua view exige (funcionario_id, mes, ano)
            link = f"{url}?funcionario_id={obj.funcionario.id}&mes={obj.data.month}&ano={obj.data.year}"
            
            return format_html(
                '<a class="button" href="{}" target="_blank" style="background-color:#666; color:white; padding:3px 8px; border-radius:3px;">'
                '<i class="fas fa-file-pdf"></i> Baixar Mês</a>',
                link
            )
        except Exception as e:
            return f"Erro URL: {e}"
            
    botao_pdf.short_description = "Folha do Mês"
    botao_pdf.allow_tags = True


@admin.register(Ferias)
class FeriasAdmin(RHAccessMixin, admin.ModelAdmin):
    autocomplete_fields = ['funcionario'] 
    
    list_display = ('funcionario', 'periodo_aquisitivo', 'data_inicio', 'status_etapas', 'acoes_rh')
    list_filter = ('status', 'abono_pecuniario')
    search_fields = ('funcionario__nome_completo',)
    
    def status_etapas(self, obj):
        agendado = "✅" if obj.data_inicio else "⬜"
        arquivo = "✅" if obj.arquivo_aviso else "⬜"
        assinado = "✅" if obj.aviso_assinado else "⬜"
        return f"1.Agenda {agendado} ➔ 2.Arq {arquivo} ➔ 3.Assinou {assinado}"
    status_etapas.short_description = "Fluxo"

    def acoes_rh(self, obj):
        if obj.status == 'Concluido':
            return mark_safe('<span style="color:green; font-weight:bold;">✅ Concluído</span>')
        
        if obj.aviso_assinado or obj.recibo_assinado:
            url = reverse('admin:ferias_aprovar', args=[obj.pk])
            return format_html(
                '''<a class="button" style="background-color: #28a745; color: white; padding: 4px 12px; border-radius: 4px; font-weight: bold;" 
                   href="{}">Aprovar</a>''',
                url
            )
        return mark_safe('<span style="color:#999;">Aguardando Docs</span>')
    
    acoes_rh.short_description = "Aprovação"
    acoes_rh.allow_tags = True

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path('<int:id>/aprovar/', self.admin_site.admin_view(self.aprovar_ferias_view), name='ferias_aprovar'),
        ]
        return my_urls + urls

    def aprovar_ferias_view(self, request, id):
        ferias = self.get_object(request, id)
        if ferias:
            ferias.status = 'Concluido'
            ferias.save()
            self.message_user(request, f"Férias de {ferias.funcionario.nome_completo} aprovadas e concluídas com sucesso!", level=messages.SUCCESS)
        return redirect(request.META.get('HTTP_REFERER', 'admin:core_rh_ferias_changelist'))

    def response_delete(self, request, obj_display, obj_id):
        messages.success(request, f"O registro de férias de {obj_display} foi excluído com sucesso.")
        return redirect('admin:core_rh_funcionario_changelist')

    def painel_aprovacao(self, obj):
        if not obj.pk: return "Salve o registro primeiro."
        if obj.status == 'Concluido':
            return mark_safe('<div style="color:green; font-weight:bold; font-size:14px; padding:10px; border:1px solid green; background:#eaffea; border-radius:5px;">✅ Processo Concluído</div>')
        
        if obj.aviso_assinado or obj.recibo_assinado:
            url = reverse('admin:ferias_aprovar', args=[obj.pk])
            return format_html(
                '''<a class="button" style="background-color: #28a745; color: white; font-weight: bold; padding: 10px 20px; border-radius: 5px; text-transform: uppercase;" href="{}"><i class="fas fa-check-circle"></i> Aprovar e Concluir Férias</a>''',
                url
            )
        return mark_safe('<span style="color:#999; font-style:italic;">Aguardando envio de documentos assinados pelo colaborador...</span>')
    
    painel_aprovacao.short_description = "Ação do RH"
    painel_aprovacao.allow_tags = True

    fieldsets = (
        ('🔍 ANÁLISE E APROVAÇÃO', {
            'fields': ('painel_aprovacao',),
            'classes': ('wide',), 
        }),
        ('PASSO 1: AGENDAR', {
            'fields': ('funcionario', ('data_inicio', 'data_fim'), ('periodo_aquisitivo', 'abono_pecuniario')),
            'classes': ('wide', 'extrapretty'), 
        }),
        ('PASSO 2: GERAR DOCUMENTO', {
            'description': 'Clique em "Salvar e Gerar PDF" abaixo. O arquivo será baixado. Depois, faça o upload aqui.',
            'fields': ('arquivo_aviso',),
        }),
        ('PASSO 3: UPLOAD DO RECIBO', {
            'fields': ('arquivo_recibo',),
        }),
        ('Status (Automático)', {
            'fields': ('status', 'aviso_assinado', 'recibo_assinado'),
            'classes': ('collapse',), 
        }),
    )
    readonly_fields = ('painel_aprovacao', 'aviso_assinado', 'recibo_assinado')

    def response_change(self, request, obj):
        if "_save_pdf" in request.POST:
            url = reverse('gerar_aviso_ferias_pdf', args=[obj.id])
            return redirect(url)
        return super().response_change(request, obj)

    def response_add(self, request, obj, post_url_continue=None):
        if "_save_pdf" in request.POST:
            url = reverse('gerar_aviso_ferias_pdf', args=[obj.id])
            return redirect(url)
        return super().response_add(request, obj, post_url_continue)


@admin.register(Contracheque)
class ContrachequeAdmin(RHAccessMixin, admin.ModelAdmin):
    list_display = ('funcionario', 'referencia', 'status_envio', 'status_assinatura', 'data_ciencia', 'link_arquivo')
    list_filter = ('ano', 'mes', 'data_ciencia')
    search_fields = ('funcionario__nome_completo', 'funcionario__matricula')
    
    def referencia(self, obj): return f"{obj.get_mes_display()}/{obj.ano}"
    def status_envio(self, obj): return mark_safe('<span style="color: green;"><i class="fas fa-check-circle"></i> Enviado</span>')
    def status_assinatura(self, obj):
        return mark_safe('<span style="color: green; font-weight: bold;"><i class="fas fa-file-signature"></i> Assinado</span>') if obj.data_ciencia else mark_safe('<span style="color: orange;"><i class="fas fa-clock"></i> Pendente</span>')
    def link_arquivo(self, obj):
        return format_html('<a href="{}" target="_blank" class="button" style="padding:5px 10px;">Ver PDF</a>', obj.arquivo.url) if obj.arquivo else "-"

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [path('importar-lote/', self.admin_site.admin_view(self.importar_lote_view), name='importar_contracheques')]
        return my_urls + urls

    def importar_lote_view(self, request):
        if request.method == "POST":
            form = UploadLoteContrachequeForm(request.POST, request.FILES)
            if form.is_valid():
                arquivo_geral = request.FILES['arquivo']
                mes = int(form.cleaned_data['mes'])
                ano = int(form.cleaned_data['ano'])
                data_recebimento = form.cleaned_data['data_recebimento']
                try:
                    self.processar_pdf(arquivo_geral, mes, ano, data_recebimento, request)
                    return redirect('admin:core_rh_contracheque_changelist')
                except Exception as e:
                    messages.error(request, f"Erro ao processar PDF: {str(e)}")
        else:
            form = UploadLoteContrachequeForm()

        return render(request, 'admin/importar_contracheques.html', {'form': form, 'title': 'Importar Contracheques', 'site_header': self.admin_site.site_header})

    def processar_pdf(self, arquivo, mes, ano, data_recebimento, request):
        if not PdfReader: raise ImportError("Instale pypdf")
        if not canvas: raise ImportError("Instale reportlab")
        
        arquivo.seek(0)
        plumber_pdf = pdfplumber.open(arquivo)
        
        arquivo.seek(0)
        reader = PdfReader(arquivo)
        
        funcionarios = Funcionario.objects.all()
        count_sucesso = 0
        nao_encontrados = []
        logs_detalhados = []

        for page_num, page in enumerate(reader.pages):
            texto_pagina = page.extract_text() or ""
            texto_pagina_upper = texto_pagina.upper()
            
            funcionario_encontrado = None
            for func in funcionarios:
                nome_upper = func.nome_completo.upper().strip()
                if nome_upper and nome_upper in texto_pagina_upper:
                    funcionario_encontrado = func
                    break
            
            if funcionario_encontrado:
                writer = PdfWriter()
                
                if data_recebimento:
                    pos_x = 130
                    pos_y = 55
                    try:
                        p_page = plumber_pdf.pages[page_num]
                        palavras = p_page.search("DATA DO RECEBIMENTO") or \
                                   p_page.search("DATA RECEBIMENTO") or \
                                   p_page.search("RECEBIMENTO")
                        
                        if palavras:
                            target = palavras[0]
                            altura_pagina = float(page.mediabox.height)
                            pos_x = target['x0'] + 15
                            pos_y = altura_pagina - target['top'] + 12
                    except Exception as e:
                        logs_detalhados.append(f"Pág {page_num+1}: Erro cálculo pos ({e})")

                    try:
                        packet = io.BytesIO()
                        can = canvas.Canvas(packet, pagesize=A4)
                        can.setFont("Helvetica", 10)
                        data_str = data_recebimento.strftime("%d/%m/%Y")
                        can.drawString(pos_x, pos_y, data_str)
                        can.setFillColorRGB(1, 0, 0) 
                        can.circle(pos_x, pos_y, 2, fill=1) 
                        can.save()

                        packet.seek(0)
                        overlay_pdf = PdfReader(packet)
                        page.merge_page(overlay_pdf.pages[0])
                    except: pass

                writer.add_page(page)
                
                pdf_bytes = io.BytesIO()
                writer.write(pdf_bytes)
                pdf_content = ContentFile(pdf_bytes.getvalue())
                
                defaults = {'arquivo': None}
                if data_recebimento: defaults['data_ciencia'] = data_recebimento

                cc, created = Contracheque.objects.update_or_create(
                    funcionario=funcionario_encontrado, mes=mes, ano=ano,
                    defaults=defaults
                )
                if not created and data_recebimento:
                    cc.data_ciencia = data_recebimento
                    cc.save()

                cc.arquivo.save(f"holerite_{funcionario_encontrado.id}.pdf", pdf_content)
                count_sucesso += 1
            else:
                nao_encontrados.append(f"Pág {page_num + 1}")
        
        plumber_pdf.close()
        
        messages.success(request, f"{count_sucesso} processados.")
        if logs_detalhados:
            msg_log = " | ".join(logs_detalhados[:3])
            messages.warning(request, f"Atenção nas datas: {msg_log}")
        if nao_encontrados: 
            messages.warning(request, f"Páginas ignoradas (sem nome): {', '.join(nao_encontrados)}")

# --- NOVOS REGISTROS (Atestados e KM) ---

@admin.register(Atestado)
class AtestadoAdmin(RHAccessMixin, admin.ModelAdmin):
    list_display = ('funcionario', 'tipo', 'data_inicio', 'qtd_dias', 'status')
    list_filter = ('status', 'tipo')
    search_fields = ('funcionario__nome_completo',)

class TrechoKMInline(admin.TabularInline):
    model = TrechoKM
    extra = 0

@admin.register(ControleKM)
class ControleKMAdmin(RHAccessMixin, admin.ModelAdmin):
    list_display = ('funcionario', 'data', 'total_km', 'status')
    list_filter = ('status', 'data', 'funcionario')
    inlines = [TrechoKMInline]
@admin.register(DespesaDiversa)
class DespesaDiversaAdmin(admin.ModelAdmin):
    list_display = ('funcionario', 'data', 'tipo', 'valor', 'status')
    list_filter = ('status', 'tipo', 'data')
    search_fields = ('funcionario__nome_completo', 'numero_chamado')
