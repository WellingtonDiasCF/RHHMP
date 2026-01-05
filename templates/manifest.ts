import { MetadataRoute } from 'next'

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: 'RHHMP App', // Nome completo do app
    short_name: 'RHHMP', // Nome curto que aparece embaixo do ícone na tela do celular
    description: 'Aplicativo de gerenciamento de perfil.',
    start_url: '/',
    display: 'standalone',
    background_color: '#0F172A', // Mesma cor do fundo do ícone
    theme_color: '#0F172A',
    icons: [
      {
        src: '/icon.svg', // O Next.js saberá usar o SVG que você colocou na raiz de 'app'
        sizes: 'any',
        type: 'image/svg+xml',
      },
    ],
  }
}