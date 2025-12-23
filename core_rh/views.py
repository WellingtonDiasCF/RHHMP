from django.db.models import Q
from django.shortcuts import render, redirect
import zipfile
import io
import os
import base64
from django.contrib.staticfiles import finders
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib.auth.views import PasswordResetView, PasswordResetDoneView
from django.contrib.auth.forms import PasswordResetForm
from django.urls import reverse_lazy
from django.utils import timezone 
from django.http import HttpResponse 
from datetime import date, time, datetime, timedelta 
from calendar import monthrange 
from django.template.loader import render_to_string 
from django.conf import settings
from .models import RegistroPonto, Funcionario, Equipe, Contracheque, Ferias, Atestado
from django.contrib import messages
from django.shortcuts import get_object_or_404
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.urls import reverse
import pdfplumber
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from django.core.files.base import ContentFile
from reportlab.lib import colors  # <--- ESSE ERA O QUE FALTAVA
from .forms import AtestadoForm

try:
    from weasyprint import HTML
except ImportError:
    print("AVISO: WeasyPrint não instalado. Instale com 'pip install weasyprint'")

import holidays 

try:
    from .models import RegistroPonto, Funcionario
except ImportError:
    print("AVISO: Modelos 'RegistroPonto' ou 'Funcionario' não encontrados.")

from .forms import CpfPasswordResetForm

User = get_user_model()
def usuario_eh_rh(user):
    """
    Retorna True se o usuário for Superuser, ou estiver na equipe 'RH' 
    (seja como principal ou secundária).
    """
    if not user.is_authenticated: return False
    if user.is_superuser: return True
    
    # Verifica grupos do Django Admin (legado)
    if user.groups.filter(name='RH').exists(): return True

    try:
        func = user.funcionario
        # Verifica Equipe Principal (Nome exato 'RH' ou 'Recursos Humanos')
        if func.equipe and func.equipe.nome in ['RH', 'Recursos Humanos', 'Gestão de Pessoas']:
            return True
        
        # Verifica Equipes Secundárias
        if func.outras_equipes.filter(nome__in=['RH', 'Recursos Humanos', 'Gestão de Pessoas']).exists():
            return True
            
    except AttributeError:
        # Usuário sem funcionário vinculado
        pass
        
    return False

DIAS_SEMANA_PT = {
    0: 'Segunda-feira', 1: 'Terça-feira', 2: 'Quarta-feira', 3: 'Quinta-feira',
    4: 'Sexta-feira', 5: 'Sábado', 6: 'Domingo'
}

MESES_PT = {
    1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
    5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
    9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
}



def get_competencia_atual():
    hoje = timezone.now()
    if hoje.day >= 16:
        if hoje.month == 12:
            return 1, hoje.year + 1
        else:
            return hoje.month + 1, hoje.year
    else:
        return hoje.month, hoje.year

def get_competencia_anterior(mes, ano):
    if mes == 1:
        return 12, ano - 1
    return mes - 1, ano

def get_datas_competencia(mes_referencia, ano_referencia):
    if mes_referencia == 1:
        mes_anterior = 12
        ano_anterior = ano_referencia - 1
    else:
        mes_anterior = mes_referencia - 1
        ano_anterior = ano_referencia
        
    data_inicio = date(ano_anterior, mes_anterior, 16)
    data_fim = date(ano_referencia, mes_referencia, 15)
    
    return data_inicio, data_fim

def calcular_horas_trabalhadas(entrada_1_str, saida_1_str, entrada_2_str, saida_2_str):
    total = timedelta()
    try:
        if entrada_1_str and saida_1_str:
            e1 = datetime.strptime(entrada_1_str, '%H:%M')
            s1 = datetime.strptime(saida_1_str, '%H:%M')
            if s1 > e1:
                total += s1 - e1
        if entrada_2_str and saida_2_str:
            e2 = datetime.strptime(entrada_2_str, '%H:%M')
            s2 = datetime.strptime(saida_2_str, '%H:%M')
            if s2 > e2:
                total += s2 - e2
    except ValueError:
        return timedelta()
    return total



# Em core_rh/views.py

@login_required 
def home(request):
    is_gestor = False
    tem_ferias = False # Padrão: Não mostra o card
    
    try:
        # Tenta pegar o funcionário vinculado ao usuário
        funcionario = Funcionario.objects.get(usuario=request.user)
        
        # Verifica se é gestor
        if funcionario.equipes_lideradas.exists():
            is_gestor = True

        # --- NOVA LÓGICA DE FÉRIAS ---
        # Só mostra o card se existir pelo menos uma férias COM ARQUIVO de aviso
        # (exclude(arquivo_aviso='') garante que o campo não está vazio)
        try:
            from .models import Ferias
            if Ferias.objects.filter(funcionario=funcionario).exclude(arquivo_aviso='').exists():
                tem_ferias = True
        except ImportError:
            pass
            
    except Funcionario.DoesNotExist: 
        pass 
    
    can_access_rh_area = usuario_eh_rh(request.user)
    
    return render(request, 'core_rh/index.html', {
        'is_gestor': is_gestor or request.user.is_superuser, 
        'can_access_rh_area': can_access_rh_area,
        'tem_ferias': tem_ferias, # Enviamos essa variável para o HTML
    })

@login_required
def salvar_ponto_view(request):
    if request.method != 'POST':
        return redirect('folha_ponto')

    try:
        mes = int(request.POST.get('mes'))
        ano = int(request.POST.get('ano'))
    except (ValueError, TypeError):
        return redirect('folha_ponto')
        
    redirect_url = reverse_lazy('folha_ponto') + f"?mes={mes}&ano={ano}"

    try:
        funcionario = Funcionario.objects.get(usuario=request.user)
    except Funcionario.DoesNotExist:
        messages.error(request, "Perfil de funcionário não encontrado.")
        return redirect('folha_ponto')

    data_inicio, data_fim = get_datas_competencia(mes, ano)

    if RegistroPonto.objects.filter(funcionario=funcionario, data__range=[data_inicio, data_fim], assinado_gestor=True).exists():
        messages.error(request, "ERRO: Esta folha já foi fechada e assinada pelo gestor. Solicite o desbloqueio ao RH.")
        return redirect(redirect_url)

    if request.FILES.get('pdf_assinado'):
        arquivo = request.FILES['pdf_assinado']
        
        
        nome_limpo = funcionario.nome_completo.strip().replace(' ', '_')
        arquivo.name = f"Folha_{nome_limpo}_{mes:02d}_{ano}_Assinado_Colab.pdf"
        
        registros = RegistroPonto.objects.filter(funcionario=funcionario, data__range=[data_inicio, data_fim])
        
        if registros.exists():
            registros.update(
                assinado_funcionario=True,
                assinado_gestor=False 
            )
            primeiro_reg = registros.first()
            primeiro_reg.arquivo_anexo = arquivo
            primeiro_reg.save()
            messages.success(request, "Documento enviado com sucesso! A assinatura do gestor foi resetada (se houver).")
        else:
             messages.error(request, "Nenhum registro de ponto encontrado para anexar o arquivo.")
        return redirect(redirect_url)

    delta_dias = (data_fim - data_inicio).days

    for i in range(delta_dias + 1):
        data_ponto = data_inicio + timedelta(days=i)
        dia_num = data_ponto.day
        
        entrada_1_str = request.POST.get(f'entrada_1_{dia_num}', '').strip()
        saida_1_str = request.POST.get(f'saida_1_{dia_num}', '').strip()
        entrada_2_str = request.POST.get(f'entrada_2_{dia_num}', '').strip()
        saida_2_str = request.POST.get(f'saida_2_{dia_num}', '').strip()
        entrada_extra_str = request.POST.get(f'entrada_extra_{dia_num}', '').strip()
        saida_extra_str = request.POST.get(f'saida_extra_{dia_num}', '').strip()
        observacoes = request.POST.get(f'observacoes_{dia_num}', '').strip()
        
        try:
            registro = RegistroPonto.objects.get(funcionario=funcionario, data=data_ponto)
            registro_existe = True
        except RegistroPonto.DoesNotExist:
            registro_existe = False
            
        if not any([entrada_1_str, saida_1_str, entrada_2_str, saida_2_str, entrada_extra_str, saida_extra_str, observacoes]):
            if registro_existe:
                registro.delete()
            continue
            
        try:
            entrada_1 = time.fromisoformat(entrada_1_str) if entrada_1_str else None
            saida_1 = time.fromisoformat(saida_1_str) if saida_1_str else None
            entrada_2 = time.fromisoformat(entrada_2_str) if entrada_2_str else None
            saida_2 = time.fromisoformat(saida_2_str) if saida_2_str else None
            entrada_extra = time.fromisoformat(entrada_extra_str) if entrada_extra_str else None
            saida_extra = time.fromisoformat(saida_extra_str) if saida_extra_str else None
        except ValueError:
            continue 

        RegistroPonto.objects.update_or_create(
            funcionario=funcionario, 
            data=data_ponto,
            defaults={
                'entrada_manha': entrada_1,    
                'saida_almoco': saida_1,      
                'volta_almoco': entrada_2,     
                'saida_tarde': saida_2,        
                'extra_entrada': entrada_extra,
                'extra_saida': saida_extra,    
                'observacao': observacoes,     
            }
        )

    if not request.FILES.get('pdf_assinado'):
        messages.success(request, "Dados de ponto salvos com sucesso!")        
    
    return redirect(redirect_url)

@login_required
def gerar_pdf_ponto_view(request):
    mes_atual, ano_atual = get_competencia_atual()
    try:
        mes = int(request.GET.get('mes', mes_atual))
        ano = int(request.GET.get('ano', ano_atual))
        target_func_id = request.GET.get('funcionario_id')
    except ValueError: return HttpResponse("Parâmetros inválidos.", status=400)

    # Verifica permissão para ver ponto de outro (Gestor ou RH)
    if target_func_id:
        try:
            alvo = Funcionario.objects.get(id=target_func_id)
            # AQUI: Usa a nova verificação de RH
            if usuario_eh_rh(request.user): 
                funcionario = alvo
            else:
                try:
                    gestor = Funcionario.objects.get(usuario=request.user)
                    # Verifica se é gestor da equipe Principal OU das Secundárias do alvo
                    equipes_alvo = [alvo.equipe] + list(alvo.outras_equipes.all())
                    equipes_que_lidero = gestor.equipes_lideradas.all()
                    
                    if any(e in equipes_que_lidero for e in equipes_alvo if e):
                        funcionario = alvo
                    else: return HttpResponse("Acesso negado.", status=403)
                except Funcionario.DoesNotExist: return HttpResponse("Perfil não encontrado.", status=403)
        except Funcionario.DoesNotExist: return HttpResponse("Funcionário não encontrado.", status=404)
    else:
        try: funcionario = Funcionario.objects.get(usuario=request.user)
        except Funcionario.DoesNotExist: return HttpResponse("Perfil não encontrado.", status=404)

    feriados_br = holidays.BR(state='DF', years=ano) 
    if hasattr(funcionario, 'estado_sigla') and funcionario.estado_sigla:
        try: feriados_br = holidays.BR(state=funcionario.estado_sigla, years=ano)
        except: pass
            
    data_inicio, data_fim = get_datas_competencia(mes, ano)
    registros_dict = {r.data.day: r for r in RegistroPonto.objects.filter(funcionario=funcionario, data__range=[data_inicio, data_fim]).order_by('data')}
    
    dias_do_mes = []
    total_horas_delta = timedelta()
    total_extras_delta = timedelta()
    
    delta_dias = (data_fim - data_inicio).days
    for i in range(delta_dias + 1):
        data_atual = data_inicio + timedelta(days=i)
        registro = registros_dict.get(data_atual.day)
        
        if registro:
            td_normal = timedelta()
            if registro.entrada_manha and registro.saida_almoco:
                dt_e1 = datetime.combine(date.min, registro.entrada_manha)
                dt_s1 = datetime.combine(date.min, registro.saida_almoco)
                if dt_s1 > dt_e1: td_normal += (dt_s1 - dt_e1)
            if registro.volta_almoco and registro.saida_tarde:
                dt_e2 = datetime.combine(date.min, registro.volta_almoco)
                dt_s2 = datetime.combine(date.min, registro.saida_tarde)
                if dt_s2 > dt_e2: td_normal += (dt_s2 - dt_e2)
            total_horas_delta += td_normal

            td_extra = timedelta()
            if registro.extra_entrada and registro.extra_saida:
                dt_ex_ent = datetime.combine(date.min, registro.extra_entrada)
                dt_ex_sai = datetime.combine(date.min, registro.extra_saida)
                if dt_ex_sai > dt_ex_ent: td_extra = dt_ex_sai - dt_ex_ent
            total_extras_delta += td_extra
            
            if td_extra.total_seconds() > 0:
                registro.horas_extra = format_delta(td_extra)
            else:
                registro.horas_extra = ""

        eh_feriado = data_atual in feriados_br
        nome_feriado = feriados_br.get(data_atual).upper() if eh_feriado else ""

        dias_do_mes.append({
            'data': data_atual,
            'dia_semana_nome': DIAS_SEMANA_PT[data_atual.weekday()],
            'eh_feriado': eh_feriado,
            'nome_feriado': nome_feriado,
            'registro': registro
        })

    logo_data = None
    possiveis_caminhos = [
        os.path.join(settings.BASE_DIR, 'core', 'static', 'images', 'dividata-logo.png'),
        os.path.join(settings.BASE_DIR, 'staticfiles', 'images', 'dividata-logo.png'),
        os.path.join(settings.BASE_DIR, 'static', 'images', 'dividata-logo.png')
    ]
    for path in possiveis_caminhos:
        if os.path.exists(path):
            try:
                with open(path, "rb") as image_file:
                    logo_data = base64.b64encode(image_file.read()).decode('utf-8')
                break
            except Exception: pass

    context = {
        'funcionario': funcionario,
        'empresa': 'Dividata Processamento de Dados Ltda', 
        'cnpj': '20.914.172/0001-88',
        'endereco': 'Praça Governador Benedito Valadares, 84 - Sobreloja, Divinópolis - MG',
        'mes_ano': f"{mes:02d}/{ano}",
        'dias_do_mes': dias_do_mes,
        'nome_mes': f"{MESES_PT[data_inicio.month]}/{MESES_PT[mes]} {ano}",
        'total_horas': format_delta(total_horas_delta),
        'total_horas_extras': format_delta(total_extras_delta),
        'user_mock': request.user,
        'logo_b64': logo_data,
    }

    html_string = render_to_string('core_rh/pdf_folha_ponto.html', context)
    response = HttpResponse(content_type='application/pdf')
    nome_func = funcionario.nome_completo.strip().replace(' ', '_')
    response['Content-Disposition'] = f'attachment; filename="Folha_{nome_func}_{mes:02d}_{ano}.pdf"'

    try:
        from weasyprint import HTML
        HTML(string=html_string, base_url=str(settings.BASE_DIR)).write_pdf(response)
    except ImportError:
        response.write(html_string)
    
    return response
@login_required
def folha_ponto_view(request):
    mes_atual_real, ano_atual_real = get_competencia_atual()
    
    try:
        mes_solicitado = int(request.GET.get('mes', mes_atual_real))
        ano_solicitado = int(request.GET.get('ano', ano_atual_real))
    except ValueError:
        mes_solicitado = mes_atual_real
        ano_solicitado = ano_atual_real
        
    mes_anterior_permitido, ano_anterior_permitido = get_competencia_anterior(mes_atual_real, ano_atual_real)
    
    is_atual = (mes_solicitado == mes_atual_real and ano_solicitado == ano_atual_real)
    is_anterior = (mes_solicitado == mes_anterior_permitido and ano_solicitado == ano_anterior_permitido)
    
    if not (is_atual or is_anterior):
        return redirect(f'{reverse_lazy("folha_ponto")}?mes={mes_atual_real}&ano={ano_atual_real}')

    prev_mes, prev_ano, next_mes, next_ano = None, None, None, None
    if is_atual:
        prev_mes, prev_ano = mes_anterior_permitido, ano_anterior_permitido
    elif is_anterior:
        next_mes, next_ano = mes_atual_real, ano_atual_real

    funcionario = None
    feriados_br = holidays.BR(state='DF', years=ano_solicitado)
    try:
        funcionario = Funcionario.objects.get(usuario=request.user)
        if hasattr(funcionario, 'estado_sigla') and funcionario.estado_sigla:
             feriados_br = holidays.BR(state=funcionario.estado_sigla, years=ano_solicitado)
    except (Funcionario.DoesNotExist, NameError):
        pass 

    data_inicio, data_fim = get_datas_competencia(mes_solicitado, ano_solicitado)
    
    dias_do_mes = []
    registros_dict = {}
    is_locked = False

    if funcionario:
        registros_banco = RegistroPonto.objects.filter(
            funcionario=funcionario, 
            data__range=[data_inicio, data_fim]
        )
        registros_dict = {r.data.day: r for r in registros_banco}
        
        if registros_banco.filter(assinado_gestor=True).exists():
            is_locked = True

    delta_dias = (data_fim - data_inicio).days
    for i in range(delta_dias + 1):
        data_atual = data_inicio + timedelta(days=i)
        
        eh_fim_de_semana = data_atual.weekday() >= 5
        eh_feriado = data_atual in feriados_br
        nome_feriado = feriados_br.get(data_atual) if eh_feriado else ""
        
        dias_do_mes.append({
            'data': data_atual,
            'dia_semana_nome': DIAS_SEMANA_PT[data_atual.weekday()],
            'eh_fim_de_semana': eh_fim_de_semana,
            'eh_feriado': eh_feriado,
            'nome_feriado': nome_feriado.upper() if nome_feriado else "",
            'registro': registros_dict.get(data_atual.day) 
        })

    mes_anterior_num = data_inicio.month
    nome_mes_composto = f"{MESES_PT[mes_anterior_num]}/{MESES_PT[mes_solicitado]}"
    
    context = {
        'dias_do_mes': dias_do_mes,
        'mes_atual': mes_solicitado, 
        'ano_atual': ano_solicitado, 
        'nome_mes': nome_mes_composto,
        'funcionario': funcionario,
        'prev_mes': prev_mes,
        'prev_ano': prev_ano,
        'next_mes': next_mes,
        'next_ano': next_ano,
        'is_locked': is_locked,
    }
    
    return render(request, 'core_rh/folha_ponto.html', context)

def mascarar_email(email):
    if not email or '@' not in email: return email
    try:
        user_part, domain_part = email.split('@')
        if len(user_part) > 2:
            masked_user = user_part[0] + "*" * (len(user_part) - 2) + user_part[-1]
            if len(masked_user) > 10: masked_user = user_part[0] + "*****" + user_part[-1]
        else:
            masked_user = user_part
        return f"{masked_user}@{domain_part}"
    except: return email

class CustomPasswordResetView(PasswordResetView):
    form_class = CpfPasswordResetForm 
    template_name = 'registration/password_reset_form.html'
    success_url = reverse_lazy('password_reset_done')

    def form_valid(self, form):
        cpf = form.cleaned_data['cpf']
        try:
            user = User.objects.get(username=cpf)
        except User.DoesNotExist:
             return super().form_valid(form)
        
        if user.email:
            reset_form = PasswordResetForm(data={'email': user.email})
            if reset_form.is_valid():
                reset_form.save(
                    request=self.request,
                    use_https=self.request.is_secure(),
                    email_template_name='registration/password_reset_email.html',
                    subject_template_name='registration/password_reset_subject.txt'
                )
                self.request.session['reset_email_masked'] = mascarar_email(user.email)
                return redirect(self.success_url)
        return super().form_valid(form)

class CustomPasswordResetDoneView(PasswordResetView):
    template_name = 'registration/password_reset_done.html'
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['masked_email'] = self.request.session.get('reset_email_masked', '')
        return context

@login_required
def area_gestor_view(request):
    try:
        gestor = Funcionario.objects.get(usuario=request.user)
        equipes_lideradas = gestor.equipes_lideradas.all()
    except Funcionario.DoesNotExist:
        return redirect('home')

    if not equipes_lideradas.exists() and not request.user.is_superuser:
        return HttpResponse("Acesso negado. Você não é gestor de nenhuma equipe.")

    # --- LÓGICA DE NAVEGAÇÃO ---
    mes_real, ano_real = get_competencia_atual()
    
    try:
        mes_solicitado = int(request.GET.get('mes', mes_real))
        ano_solicitado = int(request.GET.get('ano', ano_real))
    except ValueError:
        mes_solicitado = mes_real
        ano_solicitado = ano_real

    # Define datas para navegação
    mes_ant, ano_ant = get_competencia_anterior(mes_real, ano_real)
    
    # Variáveis de controle para os botões
    nav_anterior = None
    nav_proximo = None

    # Se estou vendo o atual, posso ir para o anterior
    if mes_solicitado == mes_real and ano_solicitado == ano_real:
        nav_anterior = {'mes': mes_ant, 'ano': ano_ant}
    
    # Se estou vendo o anterior, posso ir para o atual (Próximo)
    elif mes_solicitado == mes_ant and ano_solicitado == ano_ant:
        nav_proximo = {'mes': mes_real, 'ano': ano_real}
    
    # Se a data for inválida, reseta para o atual
    else:
        return redirect(f"{reverse('area_gestor')}?mes={mes_real}&ano={ano_real}")
    
    # ---------------------------

    data_inicio, data_fim = get_datas_competencia(mes_solicitado, ano_solicitado)
    
    funcionarios = Funcionario.objects.filter(
        equipe__in=equipes_lideradas
    ).exclude(id=gestor.id).distinct()
    
    lista_equipe = []
    
    for func in funcionarios:
        pontos = RegistroPonto.objects.filter(
            funcionario=func, 
            data__range=[data_inicio, data_fim]
        )
        
        assinado_func = pontos.filter(assinado_funcionario=True).exists()
        assinado_gest = pontos.filter(assinado_gestor=True).exists()
        pode_assinar = assinado_func and not assinado_gest
        
        ponto_com_arquivo = pontos.exclude(arquivo_anexo='').first()
        url_arquivo = ponto_com_arquivo.arquivo_anexo.url if ponto_com_arquivo and ponto_com_arquivo.arquivo_anexo else None

        nome_limpo = func.nome_completo.strip().replace(' ', '_')
        nome_download = f"Folha_{nome_limpo}_{mes_solicitado:02d}_{ano_solicitado}.pdf"

        lista_equipe.append({
            'funcionario': func,
            'status_func': assinado_func,
            'status_gestor': assinado_gest,
            'pode_assinar': pode_assinar,
            'mes': mes_solicitado,
            'ano': ano_solicitado,
            'arquivo_assinado_url': url_arquivo,
            'nome_download': nome_download,
        })

    return render(request, 'core_rh/area_gestor.html', {
        'lista_equipe': lista_equipe,
        'mes_atual': mes_solicitado,
        'ano_atual': ano_solicitado,
        'nome_mes': f"{MESES_PT[mes_solicitado]}/{ano_solicitado}",
        'nav_anterior': nav_anterior, # Passa o link para o template
        'nav_proximo': nav_proximo,   # Passa o link para o template
    })
@login_required
def assinar_ponto_gestor(request, func_id, mes, ano):
    if request.method != 'POST':
        return redirect('area_gestor')
    gestor = Funcionario.objects.get(usuario=request.user)
    equipes_gestor = gestor.equipes_lideradas.all()
    alvo = Funcionario.objects.get(id=func_id)
    
    
    equipes_alvo = [alvo.equipe] + list(alvo.outras_equipes.all())
    equipes_gestor = gestor.equipes_lideradas.all()
    
    is_authorized = any(e in equipes_gestor for e in equipes_alvo if e)

    if not is_authorized and not request.user.is_superuser:
        messages.error(request, "Permissão negada.")
        return redirect('area_gestor')
    
    data_inicio, data_fim = get_datas_competencia(int(mes), int(ano))
    
    if request.FILES.get('arquivo_gestor'):
        arquivo = request.FILES['arquivo_gestor']
        nome_limpo = alvo.nome_completo.strip().replace(' ', '_')
        arquivo.name = f"Folha_{nome_limpo}_{mes}_{ano}_Assinada_Gestor.pdf"
        
        registros = RegistroPonto.objects.filter(
            funcionario=alvo,
            data__range=[data_inicio, data_fim]
        )
        
        if registros.exists():
            
            registros.update(assinado_gestor=True)
            
            
            registro_com_arquivo = registros.exclude(arquivo_anexo='').first()
            target_reg = registro_com_arquivo if registro_com_arquivo else registros.first()
            
            
            target_reg.arquivo_anexo = arquivo
            target_reg.save()
            
            messages.success(request, f"Ponto de {alvo.nome_completo} assinado e arquivo atualizado com sucesso!")
        else:
            messages.error(request, "Registros não encontrados para o período.")
    else:
        messages.error(request, "Nenhum arquivo enviado.")
    
    return redirect('area_gestor')

@login_required
def historico_funcionario_view(request, func_id):
    funcionario = Funcionario.objects.get(id=func_id)
    
    historico = []
    hoje = timezone.now()
    
    for i in range(12):
        data_ref = hoje - timedelta(days=i*30)
        mes = data_ref.month
        ano = data_ref.year
        
        m_comp, a_comp = get_competencia_atual() if i == 0 else (mes, ano)
        
        data_ini, data_fim = get_datas_competencia(m_comp, a_comp)
        
        tem_ponto = RegistroPonto.objects.filter(
            funcionario=funcionario,
            data__range=[data_ini, data_fim]
        ).exists()
        
        if tem_ponto:
            historico.append({
                'mes': m_comp,
                'ano': a_comp,
                'nome_mes': f"{MESES_PT[m_comp]}/{a_comp}"
            })

    return render(request, 'core_rh/historico_funcionario.html', {
        'funcionario': funcionario,
        'historico': historico
    })

@login_required
def rh_summary_view(request):
    if not usuario_eh_rh(request.user):
        return HttpResponse("Acesso negado.", status=403)
    
    # --- LÓGICA DE NAVEGAÇÃO ---
    mes_real, ano_real = get_competencia_atual()
    try:
        mes_solicitado = int(request.GET.get('mes', mes_real))
        ano_solicitado = int(request.GET.get('ano', ano_real))
    except ValueError:
        mes_solicitado = mes_real
        ano_solicitado = ano_real

    mes_ant, ano_ant = get_competencia_anterior(mes_real, ano_real)
    nav_anterior = None
    nav_proximo = None

    if mes_solicitado == mes_real and ano_solicitado == ano_real:
        nav_anterior = {'mes': mes_ant, 'ano': ano_ant}
    elif mes_solicitado == mes_ant and ano_solicitado == ano_ant:
        nav_proximo = {'mes': mes_real, 'ano': ano_real}
    else:
        return redirect(f"{reverse('rh_summary')}?mes={mes_real}&ano={ano_real}")
    # ---------------------------

    data_inicio, data_fim = get_datas_competencia(mes_solicitado, ano_solicitado)
    
    todas_equipes = Equipe.objects.all().order_by('nome')
    resumo_rh = []
    
    for equipe in todas_equipes:
        membros = Funcionario.objects.filter(
            Q(equipe=equipe) | Q(outras_equipes=equipe)
        ).distinct()
        
        total_funcionarios_ativos = membros.count()
        
        membros_com_ponto = RegistroPonto.objects.filter(
            funcionario__in=membros,
            data__range=[data_inicio, data_fim]
        ).values('funcionario').distinct().count()
        
        assinados_gestor = RegistroPonto.objects.filter(
            funcionario__in=membros,
            data__range=[data_inicio, data_fim],
            assinado_gestor=True
        ).values('funcionario').distinct().count()

        resumo_rh.append({
            'equipe': equipe,
            'total_membros': total_funcionarios_ativos,
            'total_pontos_enviados': membros_com_ponto,
            'total_assinados_gestor': assinados_gestor,
            'status_formatado': f"{assinados_gestor}/{membros_com_ponto}" if membros_com_ponto > 0 else "0/0",
            'mes': mes_solicitado,
            'ano': ano_solicitado
        })

    return render(request, 'core_rh/rh_summary.html', {
        'resumo_rh': resumo_rh,
        'mes_atual': MESES_PT.get(mes_solicitado), # Nome do mês
        'mes_num': mes_solicitado, # Número para links
        'ano_atual': ano_solicitado,
        'nav_anterior': nav_anterior,
        'nav_proximo': nav_proximo,
    })

@login_required
def rh_team_detail_view(request, equipe_id):
    if not usuario_eh_rh(request.user):
        return HttpResponse("Acesso negado.", status=403)

    equipe = get_object_or_404(Equipe, id=equipe_id)
    
    # --- LÓGICA DE NAVEGAÇÃO ---
    mes_real, ano_real = get_competencia_atual()
    try:
        mes_solicitado = int(request.GET.get('mes', mes_real))
        ano_solicitado = int(request.GET.get('ano', ano_real))
    except ValueError:
        mes_solicitado = mes_real
        ano_solicitado = ano_real

    mes_ant, ano_ant = get_competencia_anterior(mes_real, ano_real)
    nav_anterior = None
    nav_proximo = None

    if mes_solicitado == mes_real and ano_solicitado == ano_real:
        nav_anterior = {'mes': mes_ant, 'ano': ano_ant}
    elif mes_solicitado == mes_ant and ano_solicitado == ano_ant:
        nav_proximo = {'mes': mes_real, 'ano': ano_real}
    else:
        return redirect(f"{reverse('rh_team_detail', args=[equipe_id])}?mes={mes_real}&ano={ano_real}")
    # ---------------------------

    data_inicio, data_fim = get_datas_competencia(mes_solicitado, ano_solicitado)

    membros = Funcionario.objects.filter(equipe=equipe).order_by('nome_completo')
    lista_colaboradores = []

    for func in membros:
        pontos_mes = RegistroPonto.objects.filter(
            funcionario=func, 
            data__range=[data_inicio, data_fim]
        )
        
        registro_status = pontos_mes.first()
        status_func = registro_status.assinado_funcionario if registro_status else False
        status_gestor = registro_status.assinado_gestor if registro_status else False
        
        anexo_reg = pontos_mes.exclude(arquivo_anexo='').first()
        url_arquivo = anexo_reg.arquivo_anexo.url if anexo_reg and anexo_reg.arquivo_anexo else None
        
        nome_limpo = func.nome_completo.strip().replace(' ', '_')
        nome_para_download = f"Folha_{nome_limpo}_{mes_solicitado:02d}_{ano_solicitado}.pdf"

        lista_colaboradores.append({
            'funcionario': func,
            'status_func': status_func,
            'status_gestor': status_gestor,
            'arquivo_anexo': url_arquivo,
            'nome_download': nome_para_download,
            'mes': mes_solicitado,
            'ano': ano_solicitado,
        })

    return render(request, 'core_rh/rh_team_detail.html', {
        'equipe': equipe,
        'lista_colaboradores': lista_colaboradores,
        'mes_atual': MESES_PT.get(mes_solicitado),
        'mes_num': mes_solicitado,
        'ano_atual': ano_solicitado,
        'nav_anterior': nav_anterior,
        'nav_proximo': nav_proximo,
    })

def rh_batch_download_view(request, equipe_id):
    """
    Gera um ZIP com todos os PDFs assinados da equipe no mês selecionado.
    Em caso de erro, redireciona de volta para a página atual com um alerta.
    """
    # 1. Captura parâmetros e Equipe
    equipe = get_object_or_404(Equipe, pk=equipe_id)
    mes = request.GET.get('mes')
    ano = request.GET.get('ano')

    # Validação básica
    if not mes or not ano:
        messages.error(request, "Mês e Ano não informados para download.")
        return redirect(request.META.get('HTTP_REFERER', '/'))

    # 2. Busca os registros com arquivo assinado
    registros = RegistroPonto.objects.filter(
        funcionario__equipe=equipe,
        data__month=mes,
        data__year=ano
    ).exclude(arquivo_anexo='').exclude(arquivo_anexo__isnull=True)

    # 3. Se não tiver arquivos, avisa e volta (NÃO renderiza página antiga)
    if not registros.exists():
        messages.warning(request, f"Nenhum ponto assinado encontrado para a equipe {equipe.nome} em {mes}/{ano}.")
        # O segredo: volta para a página de onde veio (o Admin)
        return redirect(request.META.get('HTTP_REFERER', '/'))

    # 4. Gera o ZIP em memória
    zip_buffer = io.BytesIO()
    arquivos_adicionados = 0

    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        for ponto in registros:
            try:
                # Caminho físico do arquivo
                file_path = ponto.arquivo_anexo.path
                if os.path.exists(file_path):
                    # Nome bonito dentro do ZIP: "NomeFuncionario_Data.pdf"
                    file_name = f"{ponto.funcionario.nome_completo}_{ponto.data.strftime('%d-%m-%Y')}.pdf"
                    zip_file.write(file_path, file_name)
                    arquivos_adicionados += 1
            except Exception as e:
                # Loga o erro mas tenta continuar com os outros
                print(f"Erro ao adicionar arquivo {ponto}: {e}")
                continue

    # 5. Verifica se o ZIP não ficou vazio (arquivos podem não existir no disco)
    if arquivos_adicionados == 0:
        messages.error(request, "Arquivos físicos não encontrados no servidor.")
        return redirect(request.META.get('HTTP_REFERER', '/'))

    # 6. Finaliza e entrega o download
    zip_buffer.seek(0)
    response = HttpResponse(zip_buffer, content_type='application/zip')
    nome_zip = f"Pontos_{equipe.nome}_{mes}_{ano}.zip"
    response['Content-Disposition'] = f'attachment; filename="{nome_zip}"'
    
    return response
@login_required
def rh_unlock_timesheet_view(request, func_id, mes, ano):
    if not usuario_eh_rh(request.user):
        return HttpResponse("Acesso negado. Perfil RH necessário.", status=403)
        
    funcionario = get_object_or_404(Funcionario, id=func_id)
    data_inicio, data_fim = get_datas_competencia(mes, ano)

    registros = RegistroPonto.objects.filter(
        funcionario=funcionario,
        data__range=[data_inicio, data_fim]
    )

    if registros.exists():
        registros.update(assinado_gestor=False)
        messages.success(request, f"Folha de {funcionario.nome_completo} desbloqueada com sucesso!")
    else:
        messages.error(request, "Nenhum registro encontrado para desbloquear.")

    # ALTERAÇÃO: Redireciona para a página de onde veio (HTTP_REFERER)
    # Isso permite que funcione tanto dentro do Admin quanto no Painel de RH sem mudar de tela.
    return redirect(request.META.get('HTTP_REFERER', '/'))

@login_required
def trocar_senha_obrigatoria(request):
    try:
        funcionario = request.user.funcionario
        if not funcionario.primeiro_acesso:
            return redirect('home')
    except Funcionario.DoesNotExist:
        return redirect('home')

    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            funcionario.primeiro_acesso = False
            funcionario.save()
            messages.success(request, 'Senha atualizada com sucesso! Bem-vindo.')
            return redirect('home')
        else:
            messages.error(request, 'Por favor, corrija os erros abaixo.')
    else:
        form = PasswordChangeForm(request.user)
        
    return render(request, 'core_rh/trocar_senha.html', {'form': form})

def format_delta(td):
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    return f"{hours:02}:{minutes:02}"

# core_rh/views.py (Adicione ao final)

# --- COLE ISTO NO FINAL DO ARQUIVO core_rh/views.py ---

@login_required
def admin_ponto_partial_view(request, func_id):
    """
    Retorna o HTML da folha de ponto individual para a aba do Admin.
    """
    # Verifica se é RH ou Superuser
    if not usuario_eh_rh(request.user):
        return HttpResponse("Acesso negado", status=403)

    funcionario = get_object_or_404(Funcionario, pk=func_id)
    
    # 1. Datas e Navegação
    mes_real, ano_real = get_competencia_atual()
    try:
        mes = int(request.GET.get('mes', mes_real))
        ano = int(request.GET.get('ano', ano_real))
    except ValueError:
        mes, ano = mes_real, ano_real

    # Navegação Mês Anterior
    mes_ant, ano_ant = get_competencia_anterior(mes, ano)
    
    # Navegação Mês Próximo
    if mes == 12:
        mes_prox, ano_prox = 1, ano + 1
    else:
        mes_prox, ano_prox = mes + 1, ano

    # 2. Busca Registros (Usando a função correta get_datas_competencia)
    data_inicio, data_fim = get_datas_competencia(mes, ano)
    
    registros = RegistroPonto.objects.filter(
        funcionario=funcionario,
        data__range=[data_inicio, data_fim]
    ).order_by('data')

    registros_dict = {r.data.day: r for r in registros}
    dias_do_mes = []
    
    # Feriados
    feriados_br = holidays.BR(state='DF', years=ano)
    if hasattr(funcionario, 'estado_sigla') and funcionario.estado_sigla:
         try:
             feriados_br = holidays.BR(state=funcionario.estado_sigla, years=ano)
         except: pass

    delta_dias = (data_fim - data_inicio).days
    for i in range(delta_dias + 1):
        data_atual = data_inicio + timedelta(days=i)
        eh_feriado = data_atual in feriados_br
        
        dias_do_mes.append({
            'data': data_atual,
            'dia_semana_nome': DIAS_SEMANA_PT[data_atual.weekday()],
            'eh_feriado': eh_feriado,
            'nome_feriado': feriados_br.get(data_atual).upper() if eh_feriado else "",
            'registro': registros_dict.get(data_atual.day)
        })

    context = {
        'funcionario': funcionario,
        'dias_do_mes': dias_do_mes,
        'mes_atual': mes,
        'ano_atual': ano,
        'nome_mes': f"{MESES_PT.get(mes)}/{ano}",
        'mes_anterior': mes_ant,
        'ano_anterior': ano_ant,
        'mes_proximo': mes_prox,
        'ano_proximo': ano_prox,
        'is_admin_view': True, 
    }

    # Reutiliza parte do template para não duplicar código
    return render(request, 'core_rh/includes/folha_ponto_content.html', context)


# core_rh/views.py

# core_rh/views.py

@login_required
def admin_gestor_partial_view(request):
    """
    View parcial do painel de RH (renderizada via AJAX).
    Gerencia tanto o Modo Lista (Funcionários) quanto o Modo Resumo (Equipes).
    """
    if not usuario_eh_rh(request.user):
        return HttpResponse('<div class="alert alert-danger">Acesso Negado.</div>', status=403)

    # 1. Parâmetros
    mes_real, ano_real = get_competencia_atual()
    try:
        mes = int(request.GET.get('mes', mes_real))
        ano = int(request.GET.get('ano', ano_real))
        mode = request.GET.get('mode', 'list')
        equipe_id = request.GET.get('equipe_id', '')
        estado_filtro = request.GET.get('estado', '') # Filtro de UF
        q = request.GET.get('q', '').strip() # Busca
    except ValueError:
        mes, ano = mes_real, ano_real
        mode = 'list'
        equipe_id = ''
        estado_filtro = ''
        q = ''

    # 2. Navegação de Datas
    mes_ant, ano_ant = get_competencia_anterior(mes, ano)
    if mes == 12: mes_prox, ano_prox = 1, ano + 1
    else: mes_prox, ano_prox = mes + 1, ano

    nav_anterior = {'mes': mes_ant, 'ano': ano_ant}
    nav_proximo = {'mes': mes_prox, 'ano': ano_prox}
    data_inicio, data_fim = get_datas_competencia(mes, ano)

    context = {
        'mes_atual': mes,
        'ano_atual': ano,
        'nome_mes': f"{MESES_PT.get(mes)}/{ano}",
        'nav_anterior': nav_anterior,
        'nav_proximo': nav_proximo,
        'mode': mode,
        'q': q,
        'equipe_id': equipe_id,
        'estado_filtro': estado_filtro,
    }

    # --- MODO RESUMO (CARDS DAS EQUIPES) ---
    if mode == 'summary':
        todas_equipes = Equipe.objects.all().order_by('nome')
        
        # Filtro de Busca (Nome da Equipe)
        if q:
            todas_equipes = todas_equipes.filter(nome__icontains=q)

        resumo_rh = []
        for equipe in todas_equipes:
            membros = Funcionario.objects.filter(Q(equipe=equipe) | Q(outras_equipes=equipe)).distinct()
            total = membros.count()
            assinados = RegistroPonto.objects.filter(
                funcionario__in=membros, data__range=[data_inicio, data_fim], assinado_gestor=True
            ).values('funcionario').distinct().count()
            
            progresso = int((assinados / total * 100)) if total > 0 else 0
            
            resumo_rh.append({
                'equipe': equipe,
                'total_membros': total,
                'total_assinados': assinados,
                'progresso': progresso
            })
        context['resumo_rh'] = resumo_rh

    # --- MODO LISTA (TABELA DE FUNCIONÁRIOS) ---
    else:
        funcionarios_query = Funcionario.objects.filter(usuario__is_active=True)
        
        # 1. Filtro de Estado (UF)
        if estado_filtro:
            funcionarios_query = funcionarios_query.filter(local_trabalho_estado=estado_filtro)

        # 2. Filtro de Equipe
        if equipe_id:
            try:
                eq = Equipe.objects.get(id=equipe_id)
                funcionarios_query = funcionarios_query.filter(Q(equipe=eq) | Q(outras_equipes=eq))
            except: pass
        
        # 3. Busca Texto (Nome do Funcionário)
        if q:
            funcionarios_query = funcionarios_query.filter(nome_completo__icontains=q)
            
        funcionarios = funcionarios_query.distinct().order_by('nome_completo')
        
        # Dados da Tabela
        lista_colaboradores = []
        for func in funcionarios:
            pontos = RegistroPonto.objects.filter(funcionario=func, data__range=[data_inicio, data_fim])
            
            status_func = pontos.filter(assinado_funcionario=True).exists()
            status_gestor = pontos.filter(assinado_gestor=True).exists()
            reg_anexo = pontos.exclude(arquivo_anexo='').first()
            url_anexo = reg_anexo.arquivo_anexo.url if reg_anexo and reg_anexo.arquivo_anexo else None
            
            lista_colaboradores.append({
                'funcionario': func,
                'status_func': status_func,
                'status_gestor': status_gestor,
                'arquivo_anexo': url_anexo,
                'nome_download': f"Folha_{func.nome_completo.strip().replace(' ', '_')}_{mes:02d}_{ano}.pdf",
                'mes': mes, 
                'ano': ano
            })
            
        context['lista_colaboradores'] = lista_colaboradores

        # --- DADOS PARA OS DROPDOWNS (FILTROS) ---
        # A. Estados Disponíveis
        context['estados_disponiveis'] = Funcionario.objects.exclude(local_trabalho_estado__isnull=True)\
                                            .exclude(local_trabalho_estado='')\
                                            .values_list('local_trabalho_estado', flat=True)\
                                            .distinct().order_by('local_trabalho_estado')

        # B. Equipes (Filtradas pelo Estado selecionado)
        equipes_qs = Equipe.objects.all().order_by('nome')
        if estado_filtro:
            ids_equipes_estado = Funcionario.objects.filter(local_trabalho_estado=estado_filtro)\
                                    .values_list('equipe_id', flat=True).distinct()
            equipes_qs = equipes_qs.filter(id__in=ids_equipes_estado)
            
        context['todas_equipes'] = equipes_qs

    return render(request, 'core_rh/includes/rh_area_moderno.html', context)
# --- Certifique-se que isso está no final do core_rh/views.py ---
try:
    from .models import Ferias
except ImportError:
    pass

@login_required
def minhas_ferias_view(request):
    try:
        funcionario = Funcionario.objects.get(usuario=request.user)
    except Funcionario.DoesNotExist:
        return redirect('home')
    
    lista_ferias = Ferias.objects.filter(funcionario=funcionario).order_by('-data_inicio')
    
    return render(request, 'core_rh/ferias.html', {
        'funcionario': funcionario,
        'lista_ferias': lista_ferias
    })

@login_required
def upload_ferias_view(request, ferias_id):
    if request.method != 'POST': return redirect('minhas_ferias')
    
    ferias = get_object_or_404(Ferias, id=ferias_id, funcionario__usuario=request.user)
    updated = False
    
    if request.FILES.get('aviso_file'):
        ferias.aviso_assinado = request.FILES['aviso_file']
        updated = True
        
    if request.FILES.get('recibo_file'):
        ferias.recibo_assinado = request.FILES['recibo_file']
        updated = True
        
    if updated:
        if ferias.status == 'Pendente': ferias.status = 'Enviado'
        ferias.save()
        messages.success(request, "Arquivo enviado com sucesso!")
        
    return redirect('minhas_ferias')
try:
    from weasyprint import HTML, CSS
except ImportError:
    pass

@login_required
@login_required
def gerar_aviso_ferias_pdf(request, ferias_id):
    # Garante que é admin ou RH para gerar
    if not (request.user.is_staff or usuario_eh_rh(request.user)):
        return redirect('home')
        
    ferias = get_object_or_404(Ferias, id=ferias_id)
    func = ferias.funcionario
    
    # Dados calculados
    dias_ferias = (ferias.data_fim - ferias.data_inicio).days + 1
    
    # HTML do Documento
    html_string = render_to_string('core_rh/pdf_aviso_ferias.html', {
        'ferias': ferias,
        'func': func,
        'dias_ferias': dias_ferias,
        'hoje': timezone.now()
    })

    # Gera o PDF
    # 'optimize_size' ajuda um pouco na velocidade e tamanho final
    html = HTML(string=html_string)
    pdf_file = html.write_pdf(optimize_size=('fonts', 'images'))

    # Configura o nome do arquivo
    nome_func = func.nome_completo.strip().replace(' ', '_')
    periodo_limpo = ferias.periodo_aquisitivo.replace('/', '-')
    filename = f"Notificação_de_Férias-{nome_func}-{periodo_limpo}.pdf"

    # Retorna para download (attachment força o download)
    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response
@login_required
def admin_ferias_partial_view(request):
    # --- CORREÇÃO AQUI: Usa a função usuario_eh_rh em vez de só is_staff ---
    if not (request.user.is_staff or usuario_eh_rh(request.user)):
        return HttpResponse("Acesso negado", status=403)
    # Filtros Básicos
    q = request.GET.get('q', '').strip()
    status_filtro = request.GET.get('status', '')
    mes = request.GET.get('mes')
    ano = request.GET.get('ano')

    # Data Base para Navegação (Padrão: Hoje)
    hoje = timezone.now().date()
    try:
        ano = int(ano) if ano else hoje.year
        mes = int(mes) if mes else hoje.month
        data_base = date(ano, mes, 1)
    except:
        data_base = hoje

    # Navegação Anterior/Próximo
    mes_ant = data_base.month - 1 if data_base.month > 1 else 12
    ano_ant = data_base.year if data_base.month > 1 else data_base.year - 1
    
    mes_prox = data_base.month + 1 if data_base.month < 12 else 1
    ano_prox = data_base.year if data_base.month < 12 else data_base.year + 1

    # QuerySet Inicial (Férias que cruzam o mês selecionado)
    # Lógica: Início <= Fim do Mês E Fim >= Início do Mês
    ultimo_dia_mes = monthrange(data_base.year, data_base.month)[1]
    data_fim_mes = date(data_base.year, data_base.month, ultimo_dia_mes)
    
    # Importação lazy para evitar erro circular
    from .models import Ferias, Funcionario
    
    ferias_qs = Ferias.objects.filter(
        data_inicio__lte=data_fim_mes,
        data_fim__gte=data_base
    ).select_related('funcionario', 'funcionario__equipe')

    # Filtro de Busca (Nome ou Matrícula)
    if q:
        ferias_qs = ferias_qs.filter(
            Q(funcionario__nome_completo__icontains=q) | 
            Q(funcionario__matricula__icontains=q)
        )

    # Filtro de Status
    if status_filtro:
        ferias_qs = ferias_qs.filter(status=status_filtro)

    # Ordenação
    ferias_qs = ferias_qs.order_by('data_inicio')

    context = {
        'lista_ferias': ferias_qs,
        'mes_atual': data_base.month,
        'ano_atual': data_base.year,
        'nome_mes': data_base.strftime('%B').capitalize(), # Requer locale pt-br configurado ou array manual
        'nav_anterior': {'mes': mes_ant, 'ano': ano_ant},
        'nav_proximo': {'mes': mes_prox, 'ano': ano_prox},
        'q': q,
        'status_filtro': status_filtro,
    }
    
    # Dicionário simples de meses para garantir PT-BR
    meses = {1:'Janeiro', 2:'Fevereiro', 3:'Março', 4:'Abril', 5:'Maio', 6:'Junho', 
             7:'Julho', 8:'Agosto', 9:'Setembro', 10:'Outubro', 11:'Novembro', 12:'Dezembro'}
    context['nome_mes'] = f"{meses.get(data_base.month)} {data_base.year}"

    return render(request, 'core_rh/includes/rh_ferias_moderno.html', context)

@login_required
def meus_contracheques(request):
    try:
        funcionario = request.user.funcionario
        # Pega todos os contracheques desse funcionário
        lista = Contracheque.objects.filter(funcionario=funcionario).order_by('-ano', '-mes')
    except AttributeError:
        lista = []
        messages.error(request, "Seu usuário não está vinculado a um funcionário.")

    return render(request, 'core_rh/meus_contracheques.html', {'lista': lista})

@login_required
def assinar_contracheque_local(request, pk):
    if request.method == "POST":
        contracheque = get_object_or_404(Contracheque, pk=pk, funcionario__usuario=request.user)
        
        if not contracheque.data_ciencia:
            try:
                funcionario = contracheque.funcionario
                nome_assinatura = funcionario.nome_completo.strip().upper()
                
                # Abre o arquivo
                pdf_io = io.BytesIO(contracheque.arquivo.read())
                
                # Plumber para análise geométrica
                plumber_pdf = pdfplumber.open(pdf_io)
                pdf_io.seek(0)
                reader = PdfReader(pdf_io)
                writer = PdfWriter()
                
                for i, page in enumerate(reader.pages):
                    try:
                        p_page = plumber_pdf.pages[i]
                        altura_pagina = float(page.mediabox.height)
                        
                        # 1. Encontrar a âncora de Texto ("ASSINATURA")
                        palavras = p_page.search("ASSINATURA") or \
                                   p_page.search("EMPREGADO")
                        
                        # Valores padrão iniciais (caso seja imagem escaneada sem linhas vetoriais)
                        pos_x = 400
                        pos_y_base = 50
                        largura_final = 250
                        
                        if palavras:
                            target = palavras[-1] # Pega a última ocorrência (rodapé)
                            centro_texto = (target['x0'] + target['x1']) / 2
                            
                            # --- 2. DETECÇÃO CIRÚRGICA DA LINHA ---
                            linha_exata = None
                            
                            # Define uma "zona de caça" restrita:
                            # A linha tem que estar ACIMA do texto, mas MUITO PERTO (máx 25pts / ~8mm)
                            # Se procurar muito alto, pega a tabela de valores (erro anterior)
                            limite_busca_inferior = target['top'] - 25 
                            limite_busca_superior = target['top'] 
                            
                            # Varre todas as linhas desenhadas na página
                            for linha in p_page.lines:
                                # Filtra apenas linhas horizontais (top == bottom)
                                if abs(linha['top'] - linha['bottom']) < 2:
                                    
                                    # Verifica se a linha está na "zona de caça" vertical
                                    if limite_busca_inferior < linha['bottom'] < limite_busca_superior:
                                        
                                        # Verifica se a linha está alinhada com o texto (passa por cima dele)
                                        # O centro do texto deve estar contido na largura da linha
                                        if linha['x0'] < centro_texto < linha['x1']:
                                            linha_exata = linha
                                            break # Achamos a linha da assinatura!
                            
                            if linha_exata:
                                # [SUCESSO] Usa as dimensões reais da linha encontrada
                                pos_x = linha_exata['x0']
                                largura_final = linha_exata['x1'] - linha_exata['x0']
                                
                                # Converte Y do Plumber (topo) para ReportLab (fundo)
                                pos_y_base = altura_pagina - linha_exata['bottom']
                                
                                print(f"Linha vetorial detectada! Largura: {largura_final}")
                            else:
                                # [FALLBACK] Se não achou linha (ex: PDF imagem), calcula uma largura dinâmica
                                # baseada no tamanho da palavra "ASSINATURA"
                                largura_texto = target['x1'] - target['x0']
                                largura_final = largura_texto * 3 # Estipula 3x o tamanho da palavra
                                if largura_final < 200: largura_final = 200 # Mínimo seguro
                                
                                pos_x = centro_texto - (largura_final / 2)
                                pos_y_base = altura_pagina - target['bottom']

                        # --- 3. DESENHO (WHITEOUT + NOME) ---
                        packet = io.BytesIO()
                        can = canvas.Canvas(packet, pagesize=A4)
                        
                        # Ajustes da área de limpeza
                        rect_h = 32 # Altura compacta
                        rect_y = pos_y_base - 2 # Desce um pouco para cobrir descenders
                        
                        # A. Apagar Linha Antiga (Retângulo Branco)
                        can.setFillColor(colors.white)
                        can.rect(pos_x, rect_y, largura_final, rect_h, stroke=0, fill=1)
                        
                        # B. Escrever Nome (Ajuste automático de fonte)
                        font_size = 10
                        nome_width = can.stringWidth(nome_assinatura, "Helvetica-Bold", font_size)
                        
                        # Se o nome for maior que a linha, reduz a fonte para caber
                        if nome_width > largura_final:
                            font_size = font_size * (largura_final / nome_width) * 0.95
                        
                        can.setFillColor(colors.black)
                        can.setFont("Helvetica-Bold", font_size)
                        
                        # Centraliza o nome na largura detectada
                        centro_area = pos_x + (largura_final / 2)
                        can.drawCentredString(centro_area, rect_y + 12, nome_assinatura)
                        
                        # C. Desenhar Linha Nova (Exatamente em cima da antiga)
                        can.setLineWidth(0.5)
                        y_linha = rect_y + 10
                        can.line(pos_x, y_linha, pos_x + largura_final, y_linha)
                        
                        # D. Reescrever "ASSINATURA"
                        can.setFont("Helvetica", 6)
                        can.drawCentredString(centro_area, rect_y + 2, "ASSINATURA")
                        
                        can.save()
                        packet.seek(0)
                        overlay = PdfReader(packet)
                        page.merge_page(overlay.pages[0])
                        
                    except Exception as e:
                        print(f"Erro processando página {i}: {e}")
                    
                    writer.add_page(page)
                
                plumber_pdf.close()
                
                # Salva PDF Final
                pdf_output = io.BytesIO()
                writer.write(pdf_output)
                
                filename = f"holerite_{funcionario.id}_{contracheque.mes}_{contracheque.ano}_assinado.pdf"
                contracheque.arquivo.save(filename, ContentFile(pdf_output.getvalue()), save=False)
                
                contracheque.data_ciencia = timezone.now()
                ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR')).split(',')[0]
                contracheque.ip_ciencia = ip
                contracheque.save()
                
                messages.success(request, "Assinado com sucesso!")
                
            except Exception as e:
                messages.error(request, f"Erro: {str(e)}")
        
        return redirect('meus_contracheques')
try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    PdfReader = None
    PdfWriter = None
@login_required
def admin_contracheque_partial(request):
    # 1. Filtros de Data e Busca
    hoje = timezone.now()
    try:
        mes_atual = int(request.GET.get('mes', hoje.month))
        ano_atual = int(request.GET.get('ano', hoje.year))
    except ValueError:
        mes_atual = hoje.month
        ano_atual = hoje.year

    termo_busca = request.GET.get('q', '').strip()

    # 2. Navegação (Mês Anterior / Próximo)
    mes_anterior = mes_atual - 1 if mes_atual > 1 else 12
    ano_anterior = ano_atual if mes_atual > 1 else ano_atual - 1
    
    mes_proximo = mes_atual + 1 if mes_atual < 12 else 1
    ano_proximo = ano_atual if mes_atual < 12 else ano_atual + 1

    # 3. Buscar Funcionários
    funcionarios = Funcionario.objects.all().order_by('nome_completo')
    
    if termo_busca:
        funcionarios = funcionarios.filter(nome_completo__icontains=termo_busca)

    # 4. Montar a Lista com Status
    lista_equipe = []
    
    # Busca otimizada dos contracheques do mês
    contracheques_mes = {
        cc.funcionario_id: cc 
        for cc in Contracheque.objects.filter(mes=mes_atual, ano=ano_atual)
    }

    for func in funcionarios:
        cc = contracheques_mes.get(func.id)
        
        status_envio = bool(cc and cc.arquivo)
        status_assinatura = bool(cc and cc.data_ciencia)
        
        lista_equipe.append({
            'funcionario': func,
            'contracheque': cc,
            'enviado': status_envio,
            'assinado': status_assinatura
        })

    # 5. Contexto para o Template
    context = {
        'lista_equipe': lista_equipe,
        'mes_atual': mes_atual,
        'ano_atual': ano_atual,
        'nome_mes': dict(Contracheque.MESES).get(mes_atual),
        'nav_anterior': {'mes': mes_anterior, 'ano': ano_anterior},
        'nav_proximo': {'mes': mes_proximo, 'ano': ano_proximo},
        'q': termo_busca,
        'meses_choices': Contracheque.MESES, 
    }
    
    # Aponta para o include que você criou
    return render(request, 'core_rh/includes/rh_contracheque_moderno.html', context)

# Certifique-se de ter este import no topo:
from django.urls import reverse

# Em core_rh/views.py

# Certifique-se de ter os imports:
from django.urls import reverse
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
import io

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    PdfReader = None
    PdfWriter = None

@login_required
def gerenciar_contracheques(request):
    try:
        fallback_url = reverse('admin:core_rh_funcionario_changelist')
    except:
        fallback_url = '/admin/core_rh/funcionario/'
        
    next_url = request.POST.get('next') or request.GET.get('next') or fallback_url

    if not (request.user.is_staff or usuario_eh_rh(request.user)):
        return render(request, 'core_rh/upload_log.html', {'erro_critico': 'Acesso Negado.', 'next_url': next_url})

    if request.method == 'GET':
        return redirect(next_url)

    if 'arquivo_pdf' not in request.FILES:
        return render(request, 'core_rh/upload_log.html', {'erro_critico': 'Nenhum arquivo enviado.', 'next_url': next_url})

    try:
        arquivo = request.FILES['arquivo_pdf']
        mes_upload = int(request.POST.get('mes_upload'))
        ano_upload = int(request.POST.get('ano_upload'))
        
        # Data apenas para desenho (NÃO SALVA NO BANCO)
        data_str = request.POST.get('data_recebimento')
        data_para_pdf = None
        if data_str:
            data_para_pdf = datetime.strptime(data_str, '%Y-%m-%d').date()

        arquivo.seek(0)
        plumber_pdf = pdfplumber.open(arquivo)
        arquivo.seek(0)
        reader = PdfReader(arquivo)

        funcionarios_db = Funcionario.objects.all()
        log_sucesso = []
        log_erro = []
        
        for i, page in enumerate(reader.pages):
            texto = page.extract_text() or ""
            texto_upper = texto.upper()
            
            encontrou_func = False
            funcionario_encontrado = None
            for func in funcionarios_db:
                nome_busca = func.nome_completo.strip().upper()
                if nome_busca and nome_busca in texto_upper:
                    funcionario_encontrado = func
                    encontrou_func = True
                    break 
            
            if encontrou_func:
                writer = PdfWriter()
                
                # --- APLICA A DATA VISUALMENTE (SEM ASSINAR NO SISTEMA) ---
                if data_para_pdf:
                    try:
                        p_page = plumber_pdf.pages[i]
                        altura_pagina = float(page.mediabox.height)

                        palavras_alvo = p_page.search("DATA DO RECEBIMENTO") or \
                                        p_page.search("DATA RECEBIMENTO") or \
                                        p_page.search("RECEBIMENTO")
                        
                        palavras_limite = p_page.search("Declaro ter recebido") or \
                                          p_page.search("Declaro")

                        if palavras_alvo:
                            target = palavras_alvo[0]
                            if palavras_limite:
                                limite_top = palavras_limite[0]['bottom']
                            else:
                                limite_top = target['top'] - 40

                            limite_bottom = target['bottom']
                            rect_y = altura_pagina - limite_bottom
                            rect_h = limite_bottom - limite_top
                            rect_x = target['x0'] - 20 
                            rect_w = (target['x1'] - target['x0']) + 40 

                            packet = io.BytesIO()
                            can = canvas.Canvas(packet, pagesize=A4)
                            
                            # 1. Apaga área antiga
                            can.setFillColor(colors.white)
                            can.rect(rect_x, rect_y - 2, rect_w, rect_h + 4, stroke=0, fill=1)
                            
                            # 2. Escreve Data Nova
                            altura_legenda = target['bottom'] - target['top']
                            tamanho_fonte_data = altura_legenda * 1.8
                            if tamanho_fonte_data < 12: tamanho_fonte_data = 12
                            if tamanho_fonte_data > 18: tamanho_fonte_data = 18

                            pos_data_x = target['x0']
                            pos_data_y = rect_y + 10 

                            can.setFillColor(colors.black)
                            can.setFont("Helvetica-Bold", tamanho_fonte_data)
                            can.drawString(pos_data_x, pos_data_y, data_para_pdf.strftime("%d/%m/%Y"))

                            # 3. Refaz linha e legenda
                            can.setLineWidth(0.5)
                            can.line(rect_x, rect_y + 8, rect_x + rect_w, rect_y + 8)
                            can.setFont("Helvetica", 6)
                            can.drawCentredString(rect_x + (rect_w/2), rect_y, "DATA DO RECEBIMENTO")
                            
                            can.save()
                            packet.seek(0)
                            overlay = PdfReader(packet)
                            page.merge_page(overlay.pages[0])
                    except Exception:
                        pass # Segue sem data se der erro no desenho

                writer.add_page(page)
                pdf_bytes = io.BytesIO()
                writer.write(pdf_bytes)
                
                # --- SALVA NO BANCO (SEM DATA_CIENCIA) ---
                # Removemos a lógica que setava data_ciencia aqui
                
                cc, created = Contracheque.objects.update_or_create(
                    funcionario=funcionario_encontrado, mes=mes_upload, ano=ano_upload,
                    defaults={'arquivo': None} # Reseta arquivo para salvar o novo
                )
                
                nome_arq = f"holerite_{funcionario_encontrado.id}_{mes_upload}_{ano_upload}.pdf"
                cc.arquivo.save(nome_arq, ContentFile(pdf_bytes.getvalue()))
                
                log_sucesso.append({
                    'pagina': i + 1,
                    'nome': funcionario_encontrado.nome_completo,
                    'status': 'Processado'
                })
            else:
                log_erro.append({'pagina': i + 1, 'motivo': 'Nome não encontrado.'})
        
        plumber_pdf.close()

        return render(request, 'core_rh/upload_log.html', {
            'log_sucesso': log_sucesso,
            'log_erro': log_erro,
            'total_sucesso': len(log_sucesso),
            'total_erro': len(log_erro),
            'mes_nome': dict(Contracheque.MESES).get(mes_upload, mes_upload),
            'ano': ano_upload,
            'next_url': next_url, 
        })

    except Exception as e:
        return render(request, 'core_rh/upload_log.html', {'erro_critico': str(e), 'next_url': next_url})
@login_required
def upload_individual_contracheque(request, func_id):
    if not (request.user.is_staff or usuario_eh_rh(request.user)):
        return HttpResponse("Acesso negado", status=403)
        
    if request.method == 'POST' and request.FILES.get('arquivo_individual'):
        funcionario = get_object_or_404(Funcionario, pk=func_id)
        arquivo = request.FILES['arquivo_individual']
        
        try:
            mes = int(request.POST.get('mes'))
            ano = int(request.POST.get('ano'))
            
            # Data Opcional (apenas para desenho)
            data_str = request.POST.get('data_recebimento_individual')
            data_para_pdf = None
            if data_str:
                data_para_pdf = datetime.strptime(data_str, '%Y-%m-%d').date()
                
        except (ValueError, TypeError):
            messages.error(request, "Dados inválidos.")
            return redirect(request.META.get('HTTP_REFERER', '/'))

        # --- PROCESSAMENTO DO PDF INDIVIDUAL (MESMA LÓGICA) ---
        try:
            arquivo.seek(0)
            plumber_pdf = pdfplumber.open(arquivo)
            arquivo.seek(0)
            reader = PdfReader(arquivo)
            writer = PdfWriter()

            for i, page in enumerate(reader.pages):
                if data_para_pdf:
                    try:
                        p_page = plumber_pdf.pages[i]
                        altura_pagina = float(page.mediabox.height)
                        
                        palavras_alvo = p_page.search("DATA DO RECEBIMENTO") or p_page.search("RECEBIMENTO")
                        palavras_limite = p_page.search("Declaro ter recebido") or p_page.search("Declaro")

                        if palavras_alvo:
                            target = palavras_alvo[0]
                            limite_top = palavras_limite[0]['bottom'] if palavras_limite else target['top'] - 40
                            limite_bottom = target['bottom']
                            
                            rect_y = altura_pagina - limite_bottom
                            rect_h = limite_bottom - limite_top
                            rect_x = target['x0'] - 20 
                            rect_w = (target['x1'] - target['x0']) + 40 

                            packet = io.BytesIO()
                            can = canvas.Canvas(packet, pagesize=A4)
                            
                            # Desenha Branco e Data
                            can.setFillColor(colors.white)
                            can.rect(rect_x, rect_y - 2, rect_w, rect_h + 4, stroke=0, fill=1)
                            
                            altura_legenda = target['bottom'] - target['top']
                            tamanho = max(12, min(18, altura_legenda * 1.8))
                            
                            can.setFillColor(colors.black)
                            can.setFont("Helvetica-Bold", tamanho)
                            can.drawString(target['x0'], rect_y + 10, data_para_pdf.strftime("%d/%m/%Y"))

                            can.setLineWidth(0.5)
                            can.line(rect_x, rect_y + 8, rect_x + rect_w, rect_y + 8)
                            can.setFont("Helvetica", 6)
                            can.drawCentredString(rect_x + (rect_w/2), rect_y, "DATA DO RECEBIMENTO")
                            
                            can.save()
                            packet.seek(0)
                            overlay = PdfReader(packet)
                            page.merge_page(overlay.pages[0])
                    except: pass
                
                writer.add_page(page)
            
            plumber_pdf.close()
            pdf_bytes = io.BytesIO()
            writer.write(pdf_bytes)
            
            # SALVA NO BANCO (SEM CONFIRMAR ASSINATURA)
            cc, created = Contracheque.objects.update_or_create(
                funcionario=funcionario, mes=mes, ano=ano,
                defaults={'arquivo': None}
            )
            
            nome_arq = f"holerite_{funcionario.id}_{mes}_{ano}_manual.pdf"
            cc.arquivo.save(nome_arq, ContentFile(pdf_bytes.getvalue()))
            
            messages.success(request, f"Contracheque de {funcionario.nome_completo} anexado!")

        except Exception as e:
            messages.error(request, f"Erro ao processar arquivo: {e}")
        
    return redirect(request.META.get('HTTP_REFERER', '/'))
@login_required
def excluir_contracheque(request, cc_id):
    if not (request.user.is_staff or usuario_eh_rh(request.user)):
        return HttpResponse("Acesso negado", status=403)
        
    contracheque = get_object_or_404(Contracheque, pk=cc_id)
    nome = contracheque.funcionario.nome_completo
    contracheque.delete()
    
    messages.success(request, f"Contracheque de {nome} removido com sucesso.")
    return redirect(request.META.get('HTTP_REFERER', '/'))

@login_required
def meus_atestados_view(request):
    try:
        funcionario = request.user.funcionario
    except AttributeError:
        return redirect('home')

    if request.method == 'POST':
        try:
            # Captura os dados manuais para ter controle total
            tipo = request.POST.get('tipo')
            data = request.POST.get('data_inicio')
            arquivo = request.FILES.get('arquivo')
            motivo = request.POST.get('motivo')
            
            atestado = Atestado(
                funcionario=funcionario,
                tipo=tipo,
                data_inicio=data,
                motivo=motivo,
                arquivo=arquivo
            )
            
            if tipo == 'DIAS':
                atestado.qtd_dias = int(request.POST.get('qtd_dias'))
            else: # HORAS
                atestado.hora_inicio = request.POST.get('hora_inicio')
                atestado.hora_fim = request.POST.get('hora_fim')
                atestado.qtd_dias = 0 # Zera dias para não dar erro
            
            atestado.save()
            messages.success(request, "Documento enviado com sucesso! Aguarde análise do RH.")
            
        except Exception as e:
            messages.error(request, f"Erro ao salvar: {e}")
            
        return redirect('meus_atestados')

    # Histórico
    lista = Atestado.objects.filter(funcionario=funcionario).order_by('-data_envio')
    return render(request, 'core_rh/meus_atestados.html', {'lista': lista, 'funcionario': funcionario})


# --- VIEW DO RH (LISTAGEM E AÇÃO) ---
@login_required
def rh_gestao_atestados(request):
    if not usuario_eh_rh(request.user):
        return HttpResponse("Acesso Negado", status=403)
        
    # Processa Aprovação/Recusa
    if request.method == 'POST':
        atestado_id = request.POST.get('atestado_id')
        acao = request.POST.get('acao') # 'aprovar' ou 'recusar'
        obs = request.POST.get('observacao_rh')
        
        atestado = get_object_or_404(Atestado, id=atestado_id)
        
        if acao == 'aprovar':
            atestado.status = 'Aprovado'
            atestado.observacao_rh = obs
            atestado.save()
            messages.success(request, f"Atestado de {atestado.funcionario.nome_completo} APROVADO.")
        elif acao == 'recusar':
            atestado.status = 'Recusado'
            atestado.observacao_rh = obs
            atestado.save()
            messages.warning(request, f"Atestado de {atestado.funcionario.nome_completo} RECUSADO.")
            
        return redirect('rh_gestao_atestados')

    # Filtros simples
    status_filter = request.GET.get('status', 'Pendente')
    lista = Atestado.objects.all().order_by('-data_envio')
    
    if status_filter != 'Todos':
        lista = lista.filter(status=status_filter)

    return render(request, 'core_rh/rh_gestao_atestados.html', {
        'lista': lista,
        'status_atual': status_filter
    })
@login_required
def admin_atestados_partial_view(request):
    """Renderiza a lista de atestados dentro da aba do Admin"""
    if not (request.user.is_staff or usuario_eh_rh(request.user)):
        return HttpResponse("Acesso Negado", status=403)

    # Filtros
    q = request.GET.get('q', '').strip()
    status_filtro = request.GET.get('status', 'Pendente') # Padrão: Pendente

    lista = Atestado.objects.all().select_related('funcionario').order_by('-data_envio')

    if q:
        lista = lista.filter(funcionario__nome_completo__icontains=q)

    if status_filtro and status_filtro != 'Todos':
        lista = lista.filter(status=status_filtro)

    context = {
        'lista_atestados': lista,
        'status_atual': status_filtro,
        'q': q
    }
    # Renderiza apenas o pedaço HTML (include)
    return render(request, 'core_rh/includes/rh_atestados_moderno.html', context)

@login_required
def rh_acao_atestado(request):
    """Processa a aprovação ou recusa vinda do Modal"""
    if not (request.user.is_staff or usuario_eh_rh(request.user)):
        return redirect('home')
        
    if request.method == 'POST':
        atestado_id = request.POST.get('atestado_id')
        acao = request.POST.get('acao')
        obs = request.POST.get('observacao_rh')
        
        atestado = get_object_or_404(Atestado, id=atestado_id)
        
        if acao == 'aprovar':
            atestado.status = 'Aprovado'
            atestado.observacao_rh = obs
            messages.success(request, f"Atestado de {atestado.funcionario.nome_completo} Aprovado!")
        elif acao == 'recusar':
            atestado.status = 'Recusado'
            atestado.observacao_rh = obs
            messages.warning(request, f"Atestado de {atestado.funcionario.nome_completo} Recusado.")
            
        atestado.save()
        
    # Redireciona para a mesma página (mantendo o usuário no Admin)
    return redirect(request.META.get('HTTP_REFERER', '/admin/'))