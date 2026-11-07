# POC Otimizador de Recursos (Citele)

Prova de conceito para otimizar a posição de recursos de emergência (ambulâncias, viaturas e
drones) no território, com dados oficiais.

| Pasta / arquivo | Conteúdo |
|---|---|
| `citele/` | Sistema Citele em Docker: Citeleat (motor de cálculo), Citelemap (mapa 2D) e Citeledrone (drones 3D com ARGoS). Veja `citele/README.md`. |
| `citele/divulgacao/` | Logomarca, folder, fluxo de uso, vídeo e site de divulgação. |
| `ler_areas_urbanizadas.py` | Leitura das Áreas Urbanizadas 2022 e cruzamento com municípios, bairros, setores e estados. |
| `bairros_capitais.py` | Exporta bairros (ou setores) com população das 27 capitais. |
| `*.csv` | Resultados: área urbanizada por município, população por bairro (Censo 2022), vértices de bairros e setores das capitais etc. |
| `agregados_setores/` | Agregados por setores censitários do Censo 2022 (básico, IBGE). |

Os dois CSVs maiores (`setores_capitais_pontos.csv` e
`agregados_setores/Agregados_por_setores_basico_BR.csv`) estão no **Git LFS**: instale o
[Git LFS](https://git-lfs.com) antes de clonar.

## Dados brutos (não versionados)

Os arquivos geográficos originais do IBGE são grandes e ficam fora do repositório. Para
reproduzir os resultados, baixe-os para estas pastas:

| Pasta | Origem |
|---|---|
| raiz (`AU_2026_AreasUrbanizadas_2022_Brasil.*`) | IBGE, Áreas Urbanizadas do Brasil 2022 |
| `malha_municipal/` | https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/municipio_2022/Brasil/BR/BR_Municipios_2022.zip |
| `malha_uf/` | https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/municipio_2022/Brasil/BR/BR_UF_2022.zip |
| `malha_bairros/` | https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_de_setores_censitarios__divisoes_intramunicipais/censo_2022/bairros/gpkg/BR/BR_bairros_CD2022.gpkg |
| `malha_setores/` | `.../censo_2022/setores/gpkg/UF/<UF>/<UF>_setores_CD2022.gpkg` (mesmo endereço base) |

O sistema Citele já traz em `citele/dados/` os dados processados de que precisa para rodar.
