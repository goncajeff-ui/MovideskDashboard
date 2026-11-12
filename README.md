# MovideskDashboard

Sistema de inteligência de dados e painel gerencial corporativo desenvolvido para otimizar a operação e a gestão do Suporte Técnico. A solução extrai, consolida e analisa o ciclo de vida completo dos tickets via API REST do Movidesk, fornecendo métricas de alta performance para tomada de decisão proativa, prevenção de ruptura de SLAs e monitoramento contínuo da saúde da base de clientes.

Principais Funcionalidades (Core Features)
Radar de SLA Proativo: Cálculo de Burn Rate para antecipar chamados prestes a estourar nas próximas horas, mudando a postura da operação de reativa para preditiva.

Inteligência de Cliente (Panorama e Churn): Rastreamento automático dos últimos assuntos tratados por empresa e identificação de "Clientes Silenciosos" (contagem de dias sem contato) para mitigar riscos de cancelamento.

Termômetro de Gargalos e Aging: Monitoramento de tempo ocioso (Backlog Aging) e identificação de retenção de chamados em dependências de terceiros, como filas de desenvolvimento.

Métricas de Eficiência Técnica: Acompanhamento de vazão diária (Throughput de Abertos vs. Resolvidos) e índice de Resolução no Primeiro Contato (FCR).

Gestão de Permissões: Controle de acesso granular baseado em perfis (Visualizador vs. Editor), garantindo segurança e escalabilidade na distribuição da informação até a diretoria.

Arquitetura e Stack Tecnológico
Data Ingestion (Motor de Extração): Aplicação em C# responsável pelo consumo otimizado da API Movidesk, gerenciando paginação, limites de requisição e rotinas de Carga Histórica e Carga Incremental.

Data Mart (Armazenamento e Processamento): Banco de dados relacional dedicado em Microsoft SQL Server (MSSQL). Utiliza arquitetura de tabelas Fato/Dimensão e Views avançadas em T-SQL para transferir o peso computacional das métricas para o back-end.

Apresentação (Data Visualization): Integração projetada para plataformas de Business Intelligence (como Metabase ou Apache Superset), conectando diretamente às views do SQL Server para renderização de KPIs em tempo real sem impacto no ERP da empresa.
