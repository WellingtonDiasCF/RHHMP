/* core/static/js/admin_realtime_search.js */
(function($) {
    'use strict';
    
    $(document).ready(function() {
        // Tenta pegar o jQuery do Django ou o global
        var $ = window.django ? window.django.jQuery : window.jQuery;

        console.log("RHHMP: Script de busca (Layout Personalizado) iniciado.");

        // 1. Encontra o seu input personalizado pela classe que vi no seu HTML
        var $searchInput = $('.instant-search-admin');
        
        // Se não achar pela classe, tenta pelo name genérico (backup)
        if ($searchInput.length === 0) {
            $searchInput = $('input[name="q"]');
        }

        // 2. Encontra a sua tabela personalizada pela classe .custom-table
        // (O ID #result_list não existe mais no seu template)
        var $tableRows = $('.custom-table tbody tr');

        if ($searchInput.length > 0 && $tableRows.length > 0) {
            console.log("RHHMP: Elementos encontrados. Filtro ativado.");

            $searchInput.on('keyup', function(e) {
                // Se apertar Enter, deixa o Django fazer a busca no servidor (paginação etc)
                if (e.key === 'Enter') return;

                // Texto digitado: minúsculo e sem acentos
                var term = $(this).val().toLowerCase()
                            .normalize("NFD").replace(/[\u0300-\u036f]/g, "");

                // Itera sobre as linhas da tabela .custom-table
                $tableRows.each(function() {
                    var $row = $(this);
                    
                    // Pega o texto da linha, limpa e remove acentos
                    var text = $row.text().toLowerCase()
                                .normalize("NFD").replace(/[\u0300-\u036f]/g, "");

                    // Mostra ou esconde a linha
                    if (text.indexOf(term) > -1) {
                        $row.show();
                    } else {
                        $row.hide();
                    }
                });
            });
        } else {
            console.warn("RHHMP: Não foi possível encontrar '.instant-search-admin' ou '.custom-table' na tela.");
        }
    });
})(window.django ? window.django.jQuery : window.jQuery);