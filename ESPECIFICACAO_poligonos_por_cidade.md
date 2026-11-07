# Especificação: obter os pontos dos polígonos de uma cidade e enviá-los para uma API

## Objetivo

O usuário informa o **nome da cidade** e o **estado**. O programa localiza o município,
obtém os polígonos correspondentes, extrai a lista de pontos (vértices) de cada polígono
e envia esses pontos para uma API externa, que faz os cálculos e devolve o resultado.

## Entradas

| Campo    | Exemplo            | Regras |
|----------|--------------------|--------|
| `cidade` | `Natal`, `natal`, `Ourilandia do Norte` | Obrigatório. Aceitar sem acento, com qualquer combinação de maiúsculas/minúsculas e com espaços extras. |
| `estado` | `RN`, `rn`, `Rio Grande do Norte` | Obrigatório. Aceitar a sigla ou o nome por extenso e converter sempre para a sigla (UF). |

O estado é **obrigatório** porque há municípios com o mesmo nome em UFs diferentes.
Por exemplo, existe Lagoa dos Patos em MG e há uma feição com o mesmo nome no RS.

## Dados disponíveis (já existem na pasta do projeto)

1. **`areas_urbanizadas_com_municipio.gpkg`**: as Áreas Urbanizadas 2022 do IBGE, já
   recortadas na divisa municipal. Cada feição é um polígono (ou multipolígono) de área
   urbanizada dentro de um único município. Colunas relevantes:
   - `id_area`: identificador do polígono original no shapefile do IBGE
   - `CD_MUN` (código IBGE de 7 dígitos, texto), `NM_MUN` (nome com acentos), `SIGLA_UF`
   - `Tipo`: Área urbanizada / Loteamento vazio / Outros equipamentos urbanos / Vazio intraurbano
   - `Densidade`: Densa / Pouco densa / Loteamento vazio
   - `area_km2_mun`: área em km² do polígono dentro do município
   - `geometry`: em EPSG:4674 (SIRGAS 2000, longitude/latitude em graus)
2. **`malha_municipal/BR_Municipios_2022.shp`**: os limites municipais do IBGE
   (`CD_MUN`, `NM_MUN`, `SIGLA_UF`, `geometry`), também em EPSG:4674.
3. **`ler_areas_urbanizadas.py`**: o código existente, que já tem as funções:
   - `poligonos_do_municipio(cd_mun=None, nome=None, uf=None, unir=False)`: lê os polígonos
     de área urbanizada de um município a partir do GeoPackage
   - `pontos(gdf, id_col)`: transforma polígonos numa tabela de vértices
     (`id`, `parte`, `anel`, `ordem`, `lon`, `lat`)

   Reaproveitar essas funções em vez de reescrevê-las.

Ambiente: Python 3.14, com `geopandas`, `pyogrio` e `pandas` instalados em `.venv`
(as versões estão em `requirements.txt`).

## Passo a passo

### 1. Normalizar as entradas
- Remover espaços nas pontas e espaços duplicados.
- Comparar nomes sem acento e sem diferença de maiúsculas/minúsculas
  (`unicodedata.normalize("NFKD", ...)`, remover os caracteres combinantes e usar `casefold()`).
- Tratar apóstrofos e hífens de forma equivalente, como em `Alta Floresta D'Oeste` e `Itapecerica-da-Serra`.
- Converter o estado para a sigla, usando um dicionário das 27 UFs.

### 2. Resolver o município (nome + UF → `CD_MUN`)
- Montar, uma única vez, uma tabela de busca a partir da malha municipal, com
  `CD_MUN`, `NM_MUN`, `SIGLA_UF` e o nome normalizado. Ler sem geometria, porque é rápido.
- Procurar pelo par (nome normalizado, UF):
  - **1 resultado**: seguir com o `CD_MUN` encontrado.
  - **0 resultados**: retornar um erro claro e sugerir os nomes mais parecidos daquela UF
    (por exemplo, com `difflib.get_close_matches`).
- Ignorar os códigos que não são municípios: `4300001` e `4300002` são a Lagoa Mirim e a
  Lagoa dos Patos (espelhos d'água no RS).
- A partir daqui, usar sempre o `CD_MUN`, e não o nome.

### 3. Obter os polígonos
- Chamar `poligonos_do_municipio(cd_mun=...)`.
- O município pode ter polígonos dos tipos `Polygon` e `MultiPolygon`, e ambos devem ser tratados.
- O município pode não ter nenhuma área urbanizada. Nesse caso, retornar um aviso, e não um erro genérico.
- *(A definir: ver "Decisões em aberto")* filtrar por `Tipo`/`Densidade` e/ou unir os
  polígonos (`unir=True`).

### 4. Extrair os pontos
- Chamar `pontos(gdf, "id_area")`.
- Garantir que:
  - a ordem dos vértices seja preservada (coluna `ordem`);
  - cada anel seja fechado (o último ponto é igual ao primeiro);
  - a borda externa (`anel = 0`) seja diferenciada dos buracos (`anel ≥ 1`);
  - as coordenadas fiquem em **graus decimais, com longitude antes da latitude**, em SIRGAS 2000.
- Se a API tiver limite de pontos, simplificar a geometria antes da extração
  (`geometry.simplify(tolerancia, preserve_topology=True)`), deixando a tolerância configurável.

### 5. Montar a requisição e chamar a API
- Converter os pontos para o formato esperado pela API (*a definir*). Sugestão de payload:
  ```json
  {
    "municipio": {"cd_mun": "2408102", "nome": "Natal", "uf": "RN"},
    "crs": "EPSG:4674",
    "poligonos": [
      {
        "id_area": 26345,
        "tipo": "Outros equipamentos urbanos",
        "densidade": "Densa",
        "area_km2": 0.0287,
        "aneis": [
          [[-35.182225, -5.853735], [-35.181206, -5.853735], [-35.180994, -5.856239],
           [-35.181886, -5.856154], [-35.182225, -5.853735]]
        ]
      }
    ]
  }
  ```
  Se a API aceitar GeoJSON, preferir enviar `gdf.to_json()` diretamente.
- Ler a URL e as credenciais da API de variáveis de ambiente, nunca deixá-las fixas no código.
- Definir um *timeout* e tentar de novo em caso de erro temporário (HTTP 429/5xx).
- Registrar no log o `CD_MUN`, a quantidade de polígonos e de pontos enviados e o status da resposta.

### 6. Retornar o resultado
- Devolver a resposta da API junto com a identificação do município (`CD_MUN`, `NM_MUN`, `SIGLA_UF`).

## Tratamento de erros (mensagens ao usuário)

| Situação | Comportamento |
|---|---|
| UF inválida | "Estado 'XX' não reconhecido." |
| Cidade não encontrada na UF | Mensagem com até 5 sugestões de nomes parecidos. |
| Município sem área urbanizada | Aviso, sem chamar a API. |
| API fora do ar ou com erro | Mensagem com o status HTTP; não perder os pontos já extraídos. |

## Desempenho

- O GeoPackage tem cerca de 120 MB. Usar o filtro `where` do `pyogrio`, como `poligonos_do_municipio`
  já faz, em vez de carregar o Brasil inteiro.
- Carregar a tabela de busca de municípios uma vez só e mantê-la em memória ou em cache.
- Opcional: criar um índice na coluna `CD_MUN` do GeoPackage para acelerar o filtro.

## Casos de teste (valores conhecidos)

| Entrada | Esperado |
|---|---|
| `Natal`, `RN` | `CD_MUN = 2408102`; 83 polígonos; 101,003 km²; 3.298 vértices |
| `natal`, `rio grande do norte` | o mesmo resultado acima |
| `Ourilandia do Norte`, `PA` (sem acento) | `CD_MUN = 1505437`; 47 polígonos; 15,5678 km² |
| `Lagoa dos Patos`, `MG` | `CD_MUN = 3137304` (município real) |
| `Lagoa dos Patos`, `RS` | não é município (`4300002`); retornar "não encontrado" |
| `Natal`, `PB` | não encontrado, com sugestões |
| `Sao Paulo`, `SP` | `CD_MUN = 3550308` |

Nos testes, simular a API com *mock* para não depender do serviço externo.

## Decisões em aberto (preencher antes de implementar)

1. **Quais polígonos usar:** as áreas urbanizadas do município (padrão), o limite municipal
   inteiro (`malha_municipal`) ou os dois?
2. **Filtros:** usar todos os tipos ou só `Tipo = "Área urbanizada"`? Incluir loteamentos vazios?
3. **Unir polígonos:** mandar cada polígono separado ou uni-los por município ou por tipo?
4. **API:** URL, método (POST?), autenticação, formato do payload (JSON próprio ou GeoJSON),
   limites de tamanho/pontos e formato da resposta.
5. **Interface:** função Python, linha de comando, endpoint web ou formulário?
6. **Precisão:** número de casas decimais das coordenadas (6 casas ≈ 0,1 m).
