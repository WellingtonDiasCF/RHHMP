from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordResetForm # <--- Importante
from django.core.exceptions import ValidationError
from .models import Contracheque, Atestado

User = get_user_model()

class CpfPasswordResetForm(PasswordResetForm):
    # Campo CPF visível
    cpf = forms.CharField(
        label="CPF",
        max_length=14,
        widget=forms.TextInput(attrs={
            'placeholder': '000.000.000-00',
            'class': 'form-control',
            'autofocus': True,
            'id': 'id_cpf' # Garante que o JS pegue este ID
        })
    )
    
    # Campo Email oculto (o Django exige que ele exista na classe pai)
    email = forms.CharField(required=False, widget=forms.HiddenInput())

    def clean(self):
        cleaned_data = super().clean()
        cpf_raw = cleaned_data.get('cpf', '')
        
        # Limpa o CPF (apenas números)
        cpf_limpo = ''.join(filter(str.isdigit, cpf_raw))

        if not cpf_limpo:
            raise ValidationError("Por favor, digite um CPF.")

        # Busca o usuário pelo CPF (assumindo que username = CPF)
        try:
            user = User.objects.get(username=cpf_limpo)
        except User.DoesNotExist:
            raise ValidationError("CPF não encontrado no sistema.")

        # Verifica se o usuário tem e-mail cadastrado
        if not user.email:
            raise ValidationError("Este usuário não possui um e-mail cadastrado. Contate o RH.")

        # INJEÇÃO MÁGICA: Coloca o e-mail do usuário no campo email do formulário
        # Assim, o método save() original do Django sabe para onde enviar.
        cleaned_data['email'] = user.email
        
        return cleaned_data
class UploadLoteContrachequeForm(forms.Form):
    mes = forms.ChoiceField(choices=Contracheque.MESES, label="Mês de Referência")
    ano = forms.IntegerField(label="Ano", initial=2025)
    
    # NOVO CAMPO: Data de Recebimento (Preenchimento em massa)
    data_recebimento = forms.DateField(
        label="Data do Recebimento (Assinatura)",
        required=False, # Opcional: Se deixar vazio, o funcionário assina depois
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    
    arquivo = forms.FileField(label="Arquivo PDF (Folha Completa)")

class AtestadoForm(forms.ModelForm):
    class Meta:
        model = Atestado
        # Usamos 'qtd_dias' em vez de 'dias'
        fields = ['data_inicio', 'qtd_dias', 'hora_inicio', 'hora_fim', 'motivo', 'arquivo']
        widgets = {
            'data_inicio': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'qtd_dias': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'hora_inicio': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'hora_fim': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'motivo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Gripe, Consulta, CID...'}),
            'arquivo': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,.jpg,.jpeg,.png'}),
        }