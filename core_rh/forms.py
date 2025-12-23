from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from .models import Contracheque, Atestado

User = get_user_model()

class CpfPasswordResetForm(forms.Form):
    cpf = forms.CharField(
        label="CPF",
        max_length=14,
        widget=forms.TextInput(attrs={
            'placeholder': '000.000.000-00',
            'class': 'form-control',
            'autofocus': True
        })
    )

    def clean_cpf(self):
        cpf_raw = self.cleaned_data.get('cpf', '')
        
        
        cpf_limpo = ''.join(filter(str.isdigit, cpf_raw))

        if not cpf_limpo:
            raise ValidationError("Por favor, digite um CPF.")

        
        
        if not User.objects.filter(username=cpf_limpo).exists():
            raise ValidationError("CPF não encontrado no sistema.")

        return cpf_limpo
    
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