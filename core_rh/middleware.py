from django.shortcuts import redirect
from django.urls import reverse

class TrocaSenhaObrigatoriaMiddleware:
    """
    Middleware para forçar a troca de senha no primeiro acesso
    ou logout automático se necessário.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # BLINDAGEM: Tenta pegar o funcionário, se não tiver (admin puro), ignora
            try:
                funcionario = request.user.funcionario
                
                # Se for o primeiro acesso, força a troca de senha
                if funcionario.primeiro_acesso:
                    current_url = request.path
                    # Define as URLs permitidas (para não criar loop infinito de redirecionamento)
                    # CORREÇÃO: O nome da URL no urls.py é 'trocar_senha_obrigatoria'
                    url_troca = reverse('trocar_senha_obrigatoria')
                    url_logout = reverse('logout')
                    url_admin_logout = reverse('admin:logout') 
                    
                    # Se não estiver na página de troca ou logout, redireciona
                    if current_url not in [url_troca, url_logout, url_admin_logout]:
                        return redirect('trocar_senha_obrigatoria')
            
            except AttributeError:
                # O usuário logado não tem perfil de funcionário (ex: superuser puro)
                # Segue o fluxo normal
                pass

        response = self.get_response(request)
        return response