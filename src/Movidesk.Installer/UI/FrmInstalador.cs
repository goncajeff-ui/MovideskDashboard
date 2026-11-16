using System.Diagnostics;
using System.Drawing.Drawing2D;
using System.Runtime.Versioning;
using System.Text;
using Movidesk.Installer.Core;

namespace Movidesk.Installer.UI;

[SupportedOSPlatform("windows")]
public sealed class FrmInstalador : Form
{
    private readonly InstaladorManager _instaladorManager = new();
    private readonly Image? _bgImage;
    private readonly Icon? _appIcon;

    private AuditorLog? _auditorLog;
    private CancellationTokenSource? _cts;
    private bool _instalacaoEmAndamento;
    private string _ultimoExePainel = string.Empty;
    private string _ultimoArquivoLog = string.Empty;

    // Painel esquerdo — Wizard e explicação UX
    private readonly List<StepRowWidgets> _stepWidgets = [];
    private Label _lblPassoBadge = null!;
    private Label _lblTituloExplicacao = null!;
    private Label _lblDescricaoUx = null!;

    // Inputs de configuração
    private TextBox _txtApiKey = null!;
    private Button _btnToggleApiKey = null!;
    private TextBox _txtDiretorio = null!;
    private Button _btnProcurar = null!;
    private TextBox _txtSqlHost = null!;
    private TextBox _txtSqlBanco = null!;
    private TextBox _txtSqlUsuario = null!;
    private TextBox _txtSqlSenha = null!;
    private TextBox _txtSupersetSenha = null!;
    private CheckBox _chkAtalhoDesktop = null!;
    private CheckBox _chkFirewall = null!;

    // Progresso e Console de Log
    private Label _lblStatusEtapa = null!;
    private Label _lblPercentual = null!;
    private AdviceProgressBar _progressBar = null!;
    private RichTextBox _rtbLog = null!;

    // Botões de Ação
    private Button _btnInstalar = null!;
    private Button _btnCancelar = null!;
    private Button _btnAbrirPainel = null!;
    private Button _btnAbrirSuperset = null!;
    private Button _btnAbrirLog = null!;
    private Button _btnCopiarLog = null!;

    private static readonly Color CorFundoBase = Color.FromArgb(5, 15, 28);
    private static readonly Color CorPainelEscuro = Color.FromArgb(9, 23, 40);
    private static readonly Color CorCardSecundario = Color.FromArgb(12, 31, 52);
    private static readonly Color CorCardAtivo = Color.FromArgb(16, 46, 74);
    private static readonly Color CorBordaSutil = Color.FromArgb(27, 71, 107);
    private static readonly Color CorAzulAdvice = Color.FromArgb(11, 59, 82);
    private static readonly Color CorCianoBrilho = Color.FromArgb(0, 180, 216);
    private static readonly Color CorDouradoAdvice = Color.FromArgb(197, 146, 23);
    private static readonly Color CorTextoClaro = Color.FromArgb(236, 243, 250);
    private static readonly Color CorTextoSecundario = Color.FromArgb(156, 192, 220);

    public FrmInstalador()
    {
        _bgImage = ExtratorArquivos.CarregarImagemFundo();
        _appIcon = ExtratorArquivos.CarregarIconeAdvice();

        ConfigurarFormulario();
        ConstruirLayout();
        SelecionarEtapaPreview(1, StatusEtapa.Pendente);
        RegistrarMensagemInicialConsole();
    }

    private void ConfigurarFormulario()
    {
        Text = "Instalador - Dashboard Movidesk BI";
        ClientSize = new Size(1100, 715);
        MinimumSize = new Size(1080, 660);
        StartPosition = FormStartPosition.CenterScreen;
        BackColor = CorFundoBase;
        ForeColor = CorTextoClaro;
        Font = new Font("Segoe UI", 9.5f, FontStyle.Regular);
        DoubleBuffered = true;
        SetStyle(
            ControlStyles.AllPaintingInWmPaint |
            ControlStyles.UserPaint |
            ControlStyles.OptimizedDoubleBuffer |
            ControlStyles.ResizeRedraw,
            true);

        if (_appIcon is not null)
        {
            Icon = _appIcon;
        }
    }

    protected override void OnPaintBackground(PaintEventArgs e)
    {
        if (ClientSize.Width <= 1 || ClientSize.Height <= 1)
        {
            return;
        }

        Graphics g = e.Graphics;
        g.InterpolationMode = InterpolationMode.HighQualityBicubic;
        g.SmoothingMode = SmoothingMode.AntiAlias;

        using (var baseBrush = new SolidBrush(CorFundoBase))
        {
            g.FillRectangle(baseBrush, ClientRectangle);
        }

        if (_bgImage is null)
        {
            return;
        }

        const int heroWidth = 376;
        int rightWidth = Math.Max(0, ClientSize.Width - heroWidth);

        // 1) Painel direito limpo com gradiente profissional (elimina qualquer artefato/fantasma de texto na direita)
        if (rightWidth > 0)
        {
            using (var rightBrush = new LinearGradientBrush(
                new Rectangle(heroWidth, 0, rightWidth, ClientSize.Height),
                Color.FromArgb(8, 20, 36),
                Color.FromArgb(5, 14, 26),
                LinearGradientMode.Vertical))
            {
                g.FillRectangle(rightBrush, heroWidth, 0, rightWidth, ClientSize.Height);
            }
        }

        if (_bgImage is null)
        {
            return;
        }

        // 2) Showcase fiel na lateral esquerda (Arte oficial Advice Compliance Solutions com proporção correta)
        float heroScale = (float)heroWidth / _bgImage.Width;
        float heroH = _bgImage.Height * heroScale;
        g.DrawImage(_bgImage, new RectangleF(0, 0, heroWidth, heroH));

        // Suaviza borda direita e inferior do Showcase para fundir perfeitamente aos cards
        using (var rightFeather = new LinearGradientBrush(
            new Rectangle(heroWidth - 70, 0, 72, ClientSize.Height),
            Color.FromArgb(0, 8, 20, 36),
            Color.FromArgb(255, 8, 20, 36),
            LinearGradientMode.Horizontal))
        {
            g.FillRectangle(rightFeather, heroWidth - 70, 0, 72, ClientSize.Height);
        }

        using (var bottomFeather = new LinearGradientBrush(
            new Rectangle(0, 175, heroWidth, 120),
            Color.FromArgb(15, 6, 18, 32),
            Color.FromArgb(245, 6, 18, 32),
            LinearGradientMode.Vertical))
        {
            g.FillRectangle(bottomFeather, 0, 175, heroWidth, 120);
        }

        using (var bottomSolid = new SolidBrush(Color.FromArgb(245, 6, 18, 32)))
        {
            if (ClientSize.Height > 295)
            {
                g.FillRectangle(bottomSolid, 0, 295, heroWidth, ClientSize.Height - 295);
            }
        }
    }

    private void ConstruirLayout()
    {
        SuspendLayout();

        var rootSplit = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            BackColor = Color.Transparent,
            ColumnCount = 2,
            RowCount = 1,
            Margin = Padding.Empty,
            Padding = Padding.Empty
        };
        rootSplit.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 376));
        rootSplit.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        rootSplit.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        Controls.Add(rootSplit);

        Control leftColumn = ConstruirColunaEsquerda();
        Control rightColumn = ConstruirColunaDireita();

        rootSplit.Controls.Add(leftColumn, 0, 0);
        rootSplit.Controls.Add(rightColumn, 1, 0);

        ResumeLayout(true);
    }

    private Control ConstruirColunaEsquerda()
    {
        var leftPanel = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            BackColor = Color.Transparent,
            ColumnCount = 1,
            RowCount = 3,
            Padding = new Padding(14, 12, 12, 14),
            Margin = Padding.Empty
        };
        leftPanel.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        // Linha 0: área livre para a arte ADVICE COMPLIANCE SOLUTIONS do background
        leftPanel.RowStyles.Add(new RowStyle(SizeType.Absolute, 188));
        // Linha 1: Lista dos 7 passos do Wizard
        leftPanel.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        // Linha 2: Explicação UX do passo atual
        leftPanel.RowStyles.Add(new RowStyle(SizeType.Absolute, 134));

        // Topo minimalista para manter o logotipo do background 100% visível
        var heroHeader = new Panel
        {
            Dock = DockStyle.Fill,
            BackColor = Color.Transparent,
            Margin = Padding.Empty
        };

        var lblBadgeTop = new Label
        {
            Text = "ADVICE INSTALLER 2.0",
            ForeColor = CorDouradoAdvice,
            BackColor = Color.FromArgb(200, 7, 20, 36),
            Font = new Font("Segoe UI", 8.5f, FontStyle.Bold),
            AutoSize = true,
            Padding = new Padding(8, 3, 8, 3),
            Location = new Point(2, 2)
        };
        var lblSubTop = new Label
        {
            Text = "Implantação Unificada • Movidesk BI",
            ForeColor = Color.FromArgb(190, 222, 244),
            BackColor = Color.Transparent,
            Font = new Font("Segoe UI", 8.5f, FontStyle.Regular),
            AutoSize = true,
            Location = new Point(4, 28)
        };
        heroHeader.Controls.Add(lblBadgeTop);
        heroHeader.Controls.Add(lblSubTop);
        leftPanel.Controls.Add(heroHeader, 0, 0);

        // Card de Steps
        var cardSteps = CriarCardPainel(CorPainelEscuro, CorBordaSutil);
        cardSteps.Padding = new Padding(10, 10, 10, 8);

        var stepsLayout = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            RowCount = 2,
            BackColor = Color.Transparent
        };
        stepsLayout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        stepsLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 24));
        stepsLayout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));

        var lblStepsHeader = new Label
        {
            Text = $"ROTEIRO DO ASSISTENTE ({InstaladorManager.Etapas.Count} PASSOS)",
            ForeColor = CorCianoBrilho,
            Font = new Font("Segoe UI", 8.5f, FontStyle.Bold),
            Dock = DockStyle.Fill,
            TextAlign = ContentAlignment.MiddleLeft
        };
        stepsLayout.Controls.Add(lblStepsHeader, 0, 0);

        var stepsStack = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            RowCount = InstaladorManager.Etapas.Count,
            BackColor = Color.Transparent,
            Margin = Padding.Empty
        };
        stepsStack.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));

        for (int i = 0; i < InstaladorManager.Etapas.Count; i++)
        {
            stepsStack.RowStyles.Add(new RowStyle(SizeType.Percent, 100f / InstaladorManager.Etapas.Count));
            EtapaDefinicao etapa = InstaladorManager.Etapas[i];
            StepRowWidgets row = CriarWidgetEtapa(etapa);
            _stepWidgets.Add(row);
            stepsStack.Controls.Add(row.Container, 0, i);
        }

        stepsLayout.Controls.Add(stepsStack, 0, 1);
        cardSteps.Controls.Add(stepsLayout);
        leftPanel.Controls.Add(cardSteps, 0, 1);

        // Card UX Didático ("O que este passo faz")
        var cardUx = CriarCardPainel(CorCardSecundario, CorDouradoAdvice);
        cardUx.Padding = new Padding(12, 10, 12, 10);

        var uxLayout = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            RowCount = 3,
            BackColor = Color.Transparent
        };
        uxLayout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        uxLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 20));
        uxLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 22));
        uxLayout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));

        _lblPassoBadge = new Label
        {
            Text = $"PASSO 1 DE {InstaladorManager.Etapas.Count} • GUIA DIDÁTICO",
            ForeColor = CorDouradoAdvice,
            Font = new Font("Segoe UI", 8f, FontStyle.Bold),
            Dock = DockStyle.Fill,
            TextAlign = ContentAlignment.MiddleLeft
        };

        _lblTituloExplicacao = new Label
        {
            Text = InstaladorManager.Etapas[0].Titulo,
            ForeColor = Color.White,
            Font = new Font("Segoe UI", 9.5f, FontStyle.Bold),
            Dock = DockStyle.Fill,
            TextAlign = ContentAlignment.MiddleLeft
        };

        _lblDescricaoUx = new Label
        {
            Text = InstaladorManager.Etapas[0].DescricaoUx,
            ForeColor = Color.FromArgb(215, 232, 246),
            Font = new Font("Segoe UI", 9f, FontStyle.Regular),
            Dock = DockStyle.Fill,
            TextAlign = ContentAlignment.TopLeft
        };

        uxLayout.Controls.Add(_lblPassoBadge, 0, 0);
        uxLayout.Controls.Add(_lblTituloExplicacao, 0, 1);
        uxLayout.Controls.Add(_lblDescricaoUx, 0, 2);
        cardUx.Controls.Add(uxLayout);
        leftPanel.Controls.Add(cardUx, 0, 2);

        return leftPanel;
    }

    private StepRowWidgets CriarWidgetEtapa(EtapaDefinicao etapa)
    {
        var panel = new Panel
        {
            Dock = DockStyle.Fill,
            Margin = new Padding(0, 2, 0, 2),
            Padding = new Padding(8, 2, 8, 2),
            BackColor = Color.FromArgb(12, 30, 49),
            Cursor = Cursors.Hand
        };

        var accent = new Panel
        {
            Width = 3,
            Dock = DockStyle.Left,
            BackColor = Color.Transparent
        };

        var lblIcone = new Label
        {
            Width = 26,
            Dock = DockStyle.Left,
            Text = "○",
            ForeColor = CorTextoSecundario,
            Font = new Font("Segoe UI Emoji", 10f, FontStyle.Bold),
            TextAlign = ContentAlignment.MiddleCenter
        };

        var lblTexto = new Label
        {
            Dock = DockStyle.Fill,
            Text = $"{etapa.Numero}. {etapa.Titulo}",
            ForeColor = Color.FromArgb(200, 220, 238),
            Font = new Font("Segoe UI", 9f, FontStyle.Regular),
            TextAlign = ContentAlignment.MiddleLeft,
            Padding = new Padding(4, 0, 0, 0)
        };

        panel.Controls.Add(lblTexto);
        panel.Controls.Add(lblIcone);
        panel.Controls.Add(accent);

        void OnStepPreviewClick(object? _, EventArgs __)
        {
            if (!_instalacaoEmAndamento)
            {
                SelecionarEtapaPreview(etapa.Numero, StatusEtapa.Pendente);
            }
        }

        panel.Click += OnStepPreviewClick;
        lblIcone.Click += OnStepPreviewClick;
        lblTexto.Click += OnStepPreviewClick;

        return new StepRowWidgets(etapa, panel, accent, lblIcone, lblTexto);
    }

    private Control ConstruirColunaDireita()
    {
        var rightLayout = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            BackColor = Color.Transparent,
            ColumnCount = 1,
            RowCount = 4,
            Padding = new Padding(8, 12, 16, 14),
            Margin = Padding.Empty
        };
        rightLayout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        rightLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 54));   // Cabeçalho
        rightLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 240));  // Inputs Config
        rightLayout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));   // Progresso + Console Log
        rightLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 48));   // Barra de botões

        // 1. Cabeçalho
        var headerPanel = new Panel
        {
            Dock = DockStyle.Fill,
            BackColor = Color.Transparent
        };
        var lblTitle = new Label
        {
            Text = "Instalador — Dashboard Movidesk BI",
            ForeColor = Color.White,
            Font = new Font("Segoe UI", 14.5f, FontStyle.Bold),
            Dock = DockStyle.Top,
            Height = 28,
            AutoEllipsis = true,
            TextAlign = ContentAlignment.MiddleLeft
        };
        var lblSubtitle = new Label
        {
            Text = "Provisionamento completo: Painel de Controle (.NET 8) + WSL 2 Ubuntu + Docker + Apache Superset + SQL Server ODBC 18.",
            ForeColor = CorTextoSecundario,
            Font = new Font("Segoe UI", 9f, FontStyle.Regular),
            Dock = DockStyle.Fill,
            AutoEllipsis = true,
            TextAlign = ContentAlignment.TopLeft
        };
        headerPanel.Controls.Add(lblSubtitle);
        headerPanel.Controls.Add(lblTitle);
        rightLayout.Controls.Add(headerPanel, 0, 0);

        // 2. Card de Configurações / Inputs do Usuário
        var cardConfig = CriarCardPainel(CorPainelEscuro, CorBordaSutil);
        cardConfig.Padding = new Padding(14, 10, 14, 10);

        var cfgGrid = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            RowCount = 5,
            BackColor = Color.Transparent
        };
        cfgGrid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        cfgGrid.RowStyles.Add(new RowStyle(SizeType.Absolute, 22)); // Título Card
        cfgGrid.RowStyles.Add(new RowStyle(SizeType.Absolute, 56)); // API Key
        cfgGrid.RowStyles.Add(new RowStyle(SizeType.Absolute, 52)); // Pasta Instalação
        cfgGrid.RowStyles.Add(new RowStyle(SizeType.Absolute, 52)); // SQL Server & Superset
        cfgGrid.RowStyles.Add(new RowStyle(SizeType.Percent, 100)); // Checkboxes

        var lblCfgTitle = new Label
        {
            Text = "CONFIGURAÇÃO INICIAL DO AMBIENTE",
            ForeColor = CorCianoBrilho,
            Font = new Font("Segoe UI", 8.5f, FontStyle.Bold),
            Dock = DockStyle.Fill,
            TextAlign = ContentAlignment.MiddleLeft
        };
        cfgGrid.Controls.Add(lblCfgTitle, 0, 0);

        // Linha A: Chave API Movidesk
        var apiGroup = new Panel { Dock = DockStyle.Fill, Margin = new Padding(0, 2, 0, 0) };
        var lblApiKey = new Label
        {
            Text = "Chave da API do Movidesk (Token): * — Conecta o painel aos chamados reais da operação",
            ForeColor = CorTextoClaro,
            Font = new Font("Segoe UI", 8.8f, FontStyle.Bold),
            Dock = DockStyle.Top,
            Height = 20
        };
        var apiInputRow = new TableLayoutPanel
        {
            Dock = DockStyle.Top,
            Height = 28,
            ColumnCount = 2,
            RowCount = 1,
            Margin = Padding.Empty
        };
        apiInputRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        apiInputRow.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 84));
        apiInputRow.RowStyles.Add(new RowStyle(SizeType.Percent, 100));

        _txtApiKey = CriarTextBoxEstilizado(
            textoInicial: string.Empty,
            placeholder: "Cole o Token da API Pública do Movidesk (ex.: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)",
            ocultarSenha: true);

        _btnToggleApiKey = CriarBotaoSecundario("Mostrar", width: 78);
        _btnToggleApiKey.Dock = DockStyle.Fill;
        _btnToggleApiKey.Margin = new Padding(6, 0, 0, 0);
        _btnToggleApiKey.Click += (_, _) =>
        {
            _txtApiKey.UseSystemPasswordChar = !_txtApiKey.UseSystemPasswordChar;
            _btnToggleApiKey.Text = _txtApiKey.UseSystemPasswordChar ? "Mostrar" : "Ocultar";
        };

        apiInputRow.Controls.Add(_txtApiKey, 0, 0);
        apiInputRow.Controls.Add(_btnToggleApiKey, 1, 0);
        apiGroup.Controls.Add(apiInputRow);
        apiGroup.Controls.Add(lblApiKey);
        cfgGrid.Controls.Add(apiGroup, 0, 1);

        // Linha B: Diretório de Instalação + FolderBrowserDialog
        var dirGroup = new Panel { Dock = DockStyle.Fill, Margin = new Padding(0, 2, 0, 0) };
        var lblDir = new Label
        {
            Text = "Diretório de Instalação do Painel de Controle:",
            ForeColor = CorTextoClaro,
            Font = new Font("Segoe UI", 8.8f, FontStyle.Bold),
            Dock = DockStyle.Top,
            Height = 20
        };
        var dirRow = new TableLayoutPanel
        {
            Dock = DockStyle.Top,
            Height = 28,
            ColumnCount = 2,
            RowCount = 1
        };
        dirRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        dirRow.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 104));
        dirRow.RowStyles.Add(new RowStyle(SizeType.Percent, 100));

        _txtDiretorio = CriarTextBoxEstilizado(
            textoInicial: @"C:\Advice\MovideskBI",
            placeholder: @"C:\Advice\MovideskBI");

        _btnProcurar = CriarBotaoSecundario("Procurar...", width: 98);
        _btnProcurar.Dock = DockStyle.Fill;
        _btnProcurar.Margin = new Padding(6, 0, 0, 0);
        _btnProcurar.Click += BtnProcurar_Click;

        dirRow.Controls.Add(_txtDiretorio, 0, 0);
        dirRow.Controls.Add(_btnProcurar, 1, 0);
        dirGroup.Controls.Add(dirRow);
        dirGroup.Controls.Add(lblDir);
        cfgGrid.Controls.Add(dirGroup, 0, 2);

        // Linha C: Parâmetros SQL Server & Superset
        var sqlRow = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 5,
            RowCount = 2,
            Margin = new Padding(0, 2, 0, 0)
        };
        sqlRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 24));
        sqlRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 20));
        sqlRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 16));
        sqlRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 20));
        sqlRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 20));
        sqlRow.RowStyles.Add(new RowStyle(SizeType.Absolute, 18));
        sqlRow.RowStyles.Add(new RowStyle(SizeType.Percent, 100));

        sqlRow.Controls.Add(CriarLabelCampo("SQL Server Host"), 0, 0);
        sqlRow.Controls.Add(CriarLabelCampo("Banco de Dados"), 1, 0);
        sqlRow.Controls.Add(CriarLabelCampo("Usuário SQL"), 2, 0);
        sqlRow.Controls.Add(CriarLabelCampo("Senha SQL"), 3, 0);
        sqlRow.Controls.Add(CriarLabelCampo("Senha Superset (admin)"), 4, 0);

        _txtSqlHost = CriarTextBoxEstilizado("localhost", "localhost");
        _txtSqlBanco = CriarTextBoxEstilizado("MovideskDM", "MovideskDM");
        _txtSqlUsuario = CriarTextBoxEstilizado("sa", "sa (ou vazio = Auth Windows)");
        _txtSqlSenha = CriarTextBoxEstilizado("123456", "Senha SQL", ocultarSenha: true);
        _txtSupersetSenha = CriarTextBoxEstilizado("admin", "admin", ocultarSenha: true);

        _txtSqlHost.Margin = new Padding(0, 1, 6, 0);
        _txtSqlBanco.Margin = new Padding(0, 1, 6, 0);
        _txtSqlUsuario.Margin = new Padding(0, 1, 6, 0);
        _txtSqlSenha.Margin = new Padding(0, 1, 6, 0);
        _txtSupersetSenha.Margin = new Padding(0, 1, 0, 0);

        sqlRow.Controls.Add(_txtSqlHost, 0, 1);
        sqlRow.Controls.Add(_txtSqlBanco, 1, 1);
        sqlRow.Controls.Add(_txtSqlUsuario, 2, 1);
        sqlRow.Controls.Add(_txtSqlSenha, 3, 1);
        sqlRow.Controls.Add(_txtSupersetSenha, 4, 1);
        cfgGrid.Controls.Add(sqlRow, 0, 3);

        // Linha D: Opções de implantação (Grid com 2 colunas proporcionais para evitar truncamento de texto)
        var opcoesGrid = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 2,
            RowCount = 1,
            BackColor = Color.Transparent,
            Margin = new Padding(0, 4, 0, 0),
            Padding = Padding.Empty
        };
        opcoesGrid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 55));
        opcoesGrid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 45));
        opcoesGrid.RowStyles.Add(new RowStyle(SizeType.Percent, 100));

        _chkAtalhoDesktop = new CheckBox
        {
            Text = "Criar atalho na Área de Trabalho (Painel Movidesk BI)",
            Checked = true,
            Dock = DockStyle.Fill,
            AutoEllipsis = false,
            ForeColor = CorTextoClaro,
            Font = new Font("Segoe UI", 8.8f, FontStyle.Regular),
            Margin = new Padding(0, 0, 8, 0)
        };

        _chkFirewall = new CheckBox
        {
            Text = "Liberar portas no Firewall (TCP 1433 e 8088)",
            Checked = true,
            Dock = DockStyle.Fill,
            AutoEllipsis = false,
            ForeColor = CorTextoClaro,
            Font = new Font("Segoe UI", 8.8f, FontStyle.Regular),
            Margin = new Padding(4, 0, 0, 0)
        };

        opcoesGrid.Controls.Add(_chkAtalhoDesktop, 0, 0);
        opcoesGrid.Controls.Add(_chkFirewall, 1, 0);
        cfgGrid.Controls.Add(opcoesGrid, 0, 4);

        cardConfig.Controls.Add(cfgGrid);
        rightLayout.Controls.Add(cardConfig, 0, 1);

        // 3. Card Progresso e Console Log Rico
        var cardConsole = CriarCardPainel(CorPainelEscuro, CorBordaSutil);
        cardConsole.Padding = new Padding(14, 10, 14, 12);

        var consoleGrid = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            RowCount = 3,
            BackColor = Color.Transparent
        };
        consoleGrid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        consoleGrid.RowStyles.Add(new RowStyle(SizeType.Absolute, 24));
        consoleGrid.RowStyles.Add(new RowStyle(SizeType.Absolute, 16));
        consoleGrid.RowStyles.Add(new RowStyle(SizeType.Percent, 100));

        var statusRow = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 2,
            RowCount = 1
        };
        statusRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        statusRow.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 62));
        statusRow.RowStyles.Add(new RowStyle(SizeType.Percent, 100));

        _lblStatusEtapa = new Label
        {
            Text = "⏳ Aguardando início da implantação.",
            ForeColor = Color.White,
            Font = new Font("Segoe UI", 9.2f, FontStyle.Bold),
            Dock = DockStyle.Fill,
            TextAlign = ContentAlignment.MiddleLeft
        };

        _lblPercentual = new Label
        {
            Text = "0%",
            ForeColor = CorDouradoAdvice,
            Font = new Font("Segoe UI", 9.5f, FontStyle.Bold),
            Dock = DockStyle.Fill,
            TextAlign = ContentAlignment.MiddleRight
        };

        statusRow.Controls.Add(_lblStatusEtapa, 0, 0);
        statusRow.Controls.Add(_lblPercentual, 1, 0);
        consoleGrid.Controls.Add(statusRow, 0, 0);

        _progressBar = new AdviceProgressBar
        {
            Dock = DockStyle.Fill,
            Margin = new Padding(0, 2, 0, 6)
        };
        consoleGrid.Controls.Add(_progressBar, 0, 1);

        var logBorderHost = new Panel
        {
            Dock = DockStyle.Fill,
            BackColor = Color.FromArgb(5, 13, 24),
            Padding = new Padding(8, 6, 8, 6),
            Margin = new Padding(0, 4, 0, 0)
        };

        _rtbLog = new RichTextBox
        {
            Dock = DockStyle.Fill,
            ReadOnly = true,
            BorderStyle = BorderStyle.None,
            BackColor = Color.FromArgb(5, 13, 24),
            ForeColor = Color.FromArgb(220, 234, 246),
            Font = new Font("Consolas", 9f, FontStyle.Regular),
            ScrollBars = RichTextBoxScrollBars.Vertical,
            DetectUrls = false,
            WordWrap = true
        };
        logBorderHost.Controls.Add(_rtbLog);
        consoleGrid.Controls.Add(logBorderHost, 0, 2);

        cardConsole.Controls.Add(consoleGrid);
        rightLayout.Controls.Add(cardConsole, 0, 2);

        // 4. Barra de Botões Inferior
        var actionsBar = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 2,
            RowCount = 1,
            BackColor = Color.Transparent,
            Margin = Padding.Empty,
            Padding = new Padding(0, 6, 0, 0)
        };
        actionsBar.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        actionsBar.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 250));
        actionsBar.RowStyles.Add(new RowStyle(SizeType.Percent, 100));

        var leftButtons = new FlowLayoutPanel
        {
            Dock = DockStyle.Fill,
            FlowDirection = FlowDirection.LeftToRight,
            WrapContents = false,
            Margin = Padding.Empty,
            BackColor = Color.Transparent
        };

        _btnAbrirLog = CriarBotaoSecundario("Abrir Log", width: 82);
        _btnAbrirLog.Enabled = false;
        _btnAbrirLog.Margin = new Padding(0, 4, 6, 0);
        _btnAbrirLog.Click += (_, _) => AbrirCaminhoSeguro(_ultimoArquivoLog);

        _btnCopiarLog = CriarBotaoSecundario("Copiar Log", width: 90);
        _btnCopiarLog.Enabled = true;
        _btnCopiarLog.Margin = new Padding(0, 4, 6, 0);
        _btnCopiarLog.Click += BtnCopiarLog_Click;

        _btnAbrirPainel = CriarBotaoSecundario("Painel BI", width: 92);
        _btnAbrirPainel.Enabled = false;
        _btnAbrirPainel.Margin = new Padding(0, 4, 6, 0);
        _btnAbrirPainel.Click += (_, _) => AbrirCaminhoSeguro(_ultimoExePainel);

        _btnAbrirSuperset = CriarBotaoSecundario("Superset (:8088)", width: 124);
        _btnAbrirSuperset.Enabled = false;
        _btnAbrirSuperset.Margin = new Padding(0, 4, 0, 0);
        _btnAbrirSuperset.Click += (_, _) => AbrirCaminhoSeguro("http://127.0.0.1:8088/superset/dashboard/dashboard-movidesk/");

        leftButtons.Controls.Add(_btnAbrirLog);
        leftButtons.Controls.Add(_btnCopiarLog);
        leftButtons.Controls.Add(_btnAbrirPainel);
        leftButtons.Controls.Add(_btnAbrirSuperset);

        var rightButtons = new FlowLayoutPanel
        {
            Dock = DockStyle.Fill,
            FlowDirection = FlowDirection.RightToLeft,
            WrapContents = false,
            Margin = Padding.Empty,
            BackColor = Color.Transparent
        };

        _btnInstalar = new Button
        {
            Text = "Iniciar Instalação",
            Width = 152,
            Height = 36,
            FlatStyle = FlatStyle.Flat,
            BackColor = CorDouradoAdvice,
            ForeColor = Color.FromArgb(10, 20, 32),
            Font = new Font("Segoe UI", 9.5f, FontStyle.Bold),
            Cursor = Cursors.Hand,
            Margin = new Padding(6, 0, 0, 0)
        };
        _btnInstalar.FlatAppearance.BorderSize = 0;
        _btnInstalar.Click += BtnInstalar_Click;

        _btnCancelar = CriarBotaoSecundario("Cancelar", width: 90);
        _btnCancelar.Height = 36;
        _btnCancelar.Enabled = false;
        _btnCancelar.Margin = Padding.Empty;
        _btnCancelar.Click += BtnCancelar_Click;

        rightButtons.Controls.Add(_btnInstalar);
        rightButtons.Controls.Add(_btnCancelar);

        actionsBar.Controls.Add(leftButtons, 0, 0);
        actionsBar.Controls.Add(rightButtons, 1, 0);
        rightLayout.Controls.Add(actionsBar, 0, 3);

        return rightLayout;
    }

    private void BtnProcurar_Click(object? sender, EventArgs e)
    {
        using var dialog = new FolderBrowserDialog
        {
            Description = "Escolha o diretório onde o Painel de Controle Movidesk BI será instalado:",
            UseDescriptionForTitle = true,
            ShowNewFolderButton = true
        };

        string atual = _txtDiretorio.Text.Trim();
        if (!string.IsNullOrWhiteSpace(atual) && Directory.Exists(atual))
        {
            dialog.SelectedPath = atual;
        }
        else if (Directory.Exists(@"C:\Advice"))
        {
            dialog.SelectedPath = @"C:\Advice";
        }

        if (dialog.ShowDialog(this) == DialogResult.OK && !string.IsNullOrWhiteSpace(dialog.SelectedPath))
        {
            _txtDiretorio.Text = dialog.SelectedPath;
        }
    }

    private async void BtnInstalar_Click(object? sender, EventArgs e)
    {
        if (_instalacaoEmAndamento)
        {
            return;
        }

        if (!ValidarEntradas(out ConfiguracaoInstalacao? config))
        {
            return;
        }

        _instalacaoEmAndamento = true;
        _cts?.Dispose();
        _cts = new CancellationTokenSource();

        _auditorLog?.Dispose();
        _auditorLog = new AuditorLog();
        _ultimoArquivoLog = _auditorLog.CaminhoArquivoLog;
        _auditorLog.OnLogEmitido += RegistrarLogNoConsoleSafe;

        _rtbLog.Clear();
        ResetarEstadoVisualEtapas();
        AlternarEstadoControlesDuranteExecucao(emExecucao: true);

        _btnAbrirLog.Enabled = true;
        _btnAbrirPainel.Enabled = false;
        _btnAbrirSuperset.Enabled = false;

        var progressReporter = new Progress<ProgressoEtapa>(AtualizarProgressoEtapa);

        try
        {
            _auditorLog.Info($"Diretório escolhido: {config!.DiretorioInstalacao}");
            _auditorLog.Info($"Arquivo de auditoria: {_auditorLog.CaminhoArquivoLog}");

            ResultadoInstalacao resultado = await _instaladorManager.ExecutarInstalacaoCompletaAsync(
                config,
                _auditorLog,
                progressReporter,
                _cts.Token);

            _ultimoExePainel = resultado.CaminhoExecutavelPainel;
            _ultimoArquivoLog = resultado.CaminhoArquivoLog;

            FinalizarInterfaceAposInstalacao(resultado);
        }
        catch (Exception ex)
        {
            _auditorLog?.Erro($"Erro inesperado durante a execução: {ex.Message}");
            _lblStatusEtapa.Text = "❌ Falha na implantação. Consulte o console de log.";
            _lblStatusEtapa.ForeColor = Color.FromArgb(248, 113, 113);

            string resumo = FormatarMensagemDialogoErro(ex.Message);
            MessageBox.Show(
                this,
                $"Não foi possível concluir a instalação:\n\n{resumo}\n\nUse o botão 'Copiar Log' ou 'Abrir Log' para visualizar e compartilhar os detalhes completos.",
                "Erro — Instalador Dashboard Movidesk BI",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
        }
        finally
        {
            _instalacaoEmAndamento = false;
            AlternarEstadoControlesDuranteExecucao(emExecucao: false);
        }
    }

    private void BtnCancelar_Click(object? sender, EventArgs e)
    {
        if (!_instalacaoEmAndamento || _cts is null || _cts.IsCancellationRequested)
        {
            return;
        }

        DialogResult resp = MessageBox.Show(
            this,
            "Deseja realmente cancelar a implantação em andamento?",
            "Confirmar Cancelamento — Advice Installer 2.0",
            MessageBoxButtons.YesNo,
            MessageBoxIcon.Question);

        if (resp == DialogResult.Yes)
        {
            _btnCancelar.Enabled = false;
            _lblStatusEtapa.Text = "⏳ Solicitando interrupção segura dos processos...";
            _auditorLog?.Aviso("Solicitação de cancelamento enviada pelo usuário...");
            _cts.Cancel();
        }
    }

    private void FinalizarInterfaceAposInstalacao(ResultadoInstalacao resultado)
    {
        if (File.Exists(resultado.CaminhoExecutavelPainel))
        {
            _btnAbrirPainel.Enabled = true;
        }

        if (resultado.ReinicioWindowsNecessario)
        {
            _lblStatusEtapa.Text = "⚠ Reinicialização do Windows necessária para concluir o WSL 2.";
            _lblStatusEtapa.ForeColor = Color.FromArgb(251, 191, 36);

            MessageBox.Show(
                this,
                resultado.MensagemResumo,
                "Reinicialização Necessária — WSL 2",
                MessageBoxButtons.OK,
                MessageBoxIcon.Warning);
            return;
        }

        if (resultado.Cancelada)
        {
            _lblStatusEtapa.Text = "⚠ Implantação cancelada pelo operador.";
            _lblStatusEtapa.ForeColor = Color.FromArgb(251, 191, 36);
            return;
        }

        if (!resultado.Sucesso)
        {
            _lblStatusEtapa.Text = "❌ Implantação interrompida por erro. Verifique o log acima.";
            _lblStatusEtapa.ForeColor = Color.FromArgb(248, 113, 113);

            string resumo = FormatarMensagemDialogoErro(resultado.MensagemResumo);
            string infoLog = string.IsNullOrWhiteSpace(resultado.CaminhoArquivoLog)
                ? string.Empty
                : $"\n\nArquivo de log completo:\n{resultado.CaminhoArquivoLog}";

            MessageBox.Show(
                this,
                $"Ocorreu uma falha durante a implantação:\n\n{resumo}{infoLog}\n\nUse o botão 'Copiar Log' ou 'Abrir Log' para compartilhar os detalhes.",
                "Falha na Implantação — Dashboard Movidesk BI",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            return;
        }

        _btnAbrirSuperset.Enabled = true;
        _progressBar.Value = 100;
        _lblPercentual.Text = "100%";

        if (resultado.DeployDashboardPendenteBanco)
        {
            _lblStatusEtapa.Text = "⚠ Infraestrutura pronta! Setup final aguarda o banco MovideskDM.";
            _lblStatusEtapa.ForeColor = Color.FromArgb(251, 191, 36);

            MessageBox.Show(
                this,
                $"{resultado.MensagemResumo}\n\n" +
                $"Painel instalado em: {resultado.DiretorioInstalacao}\n" +
                $"Scripts SQL salvos em: {Path.Combine(resultado.DiretorioInstalacao, "database")}",
                "Instalação Concluída com Aviso — Dashboard Movidesk BI",
                MessageBoxButtons.OK,
                MessageBoxIcon.Information);
        }
        else
        {
            _lblStatusEtapa.Text = "✔ Implantação unificada concluída com sucesso!";
            _lblStatusEtapa.ForeColor = Color.FromArgb(52, 211, 153);

            string infoAtalho = string.IsNullOrWhiteSpace(resultado.CaminhoAtalhoDesktop)
                ? "Painel disponível na pasta de instalação."
                : $"Atalho criado: {Path.GetFileName(resultado.CaminhoAtalhoDesktop)} (Área de Trabalho)";

            MessageBox.Show(
                this,
                "Instalação concluída com 100% de sucesso!\n\n" +
                $"• Painel de Controle: {resultado.DiretorioInstalacao}\n" +
                $"• {infoAtalho}\n" +
                $"• Apache Superset: {resultado.UrlDashboard}\n\n" +
                "Você já pode abrir o Painel de Controle ou acessar o Dashboard - Movidesk BI.",
                "Advice Installer 2.0 — Sucesso",
                MessageBoxButtons.OK,
                MessageBoxIcon.Information);
        }
    }

    private bool ValidarEntradas(out ConfiguracaoInstalacao? config)
    {
        config = null;

        string apiKey = _txtApiKey.Text.Trim();
        if (string.IsNullOrWhiteSpace(apiKey))
        {
            MessageBox.Show(
                this,
                "Por favor, informe a Chave da API (Token) do Movidesk.\n\nEla será gravada no appsettings.json para conectar o Painel de Controle aos chamados reais.",
                "Campo Obrigatório — Chave da API",
                MessageBoxButtons.OK,
                MessageBoxIcon.Warning);
            _txtApiKey.Focus();
            return false;
        }

        string dir = _txtDiretorio.Text.Trim();
        if (string.IsNullOrWhiteSpace(dir))
        {
            MessageBox.Show(
                this,
                "Por favor, selecione o diretório de instalação do Painel de Controle.",
                "Campo Obrigatório — Diretório",
                MessageBoxButtons.OK,
                MessageBoxIcon.Warning);
            _txtDiretorio.Focus();
            return false;
        }

        try
        {
            dir = Path.GetFullPath(dir);
            Directory.CreateDirectory(dir);
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                this,
                $"Não foi possível validar ou criar o diretório '{dir}':\n{ex.Message}",
                "Diretório Inválido",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            _txtDiretorio.Focus();
            return false;
        }

        if (string.IsNullOrWhiteSpace(_txtSupersetSenha.Text))
        {
            MessageBox.Show(
                this,
                "Informe a senha que será definida para o usuário 'admin' do Apache Superset.",
                "Campo Obrigatório — Senha Superset",
                MessageBoxButtons.OK,
                MessageBoxIcon.Warning);
            _txtSupersetSenha.Focus();
            return false;
        }

        config = new ConfiguracaoInstalacao
        {
            ApiKey = apiKey,
            DiretorioInstalacao = dir,
            SqlServerHost = string.IsNullOrWhiteSpace(_txtSqlHost.Text) ? "localhost" : _txtSqlHost.Text.Trim(),
            SqlServerBanco = string.IsNullOrWhiteSpace(_txtSqlBanco.Text) ? "MovideskDM" : _txtSqlBanco.Text.Trim(),
            SqlServerUsuario = _txtSqlUsuario.Text.Trim(),
            SqlServerSenha = _txtSqlSenha.Text,
            SupersetSenhaAdmin = _txtSupersetSenha.Text,
            CriarAtalhoDesktop = _chkAtalhoDesktop.Checked,
            ConfigurarFirewall = _chkFirewall.Checked
        };

        return true;
    }

    private void AtualizarProgressoEtapa(ProgressoEtapa prog)
    {
        if (IsDisposed || Disposing)
        {
            return;
        }

        SelecionarEtapaPreview(prog.EtapaAtual, prog.Status);

        string simbolo = prog.Status switch
        {
            StatusEtapa.Concluida => "✔",
            StatusEtapa.Aviso => "⚠",
            StatusEtapa.Erro => "❌",
            _ => "⏳"
        };

        _lblStatusEtapa.Text = $"{simbolo} Passo {prog.EtapaAtual}/{prog.TotalEtapas}: {prog.TituloEtapa}";
        _lblStatusEtapa.ForeColor = prog.Status switch
        {
            StatusEtapa.Concluida => Color.FromArgb(52, 211, 153),
            StatusEtapa.Aviso => Color.FromArgb(251, 191, 36),
            StatusEtapa.Erro => Color.FromArgb(248, 113, 113),
            _ => Color.White
        };

        _progressBar.Value = prog.PercentualGeral;
        _lblPercentual.Text = $"{prog.PercentualGeral}%";
    }

    private void SelecionarEtapaPreview(int numeroEtapa, StatusEtapa statusAtual)
    {
        if (numeroEtapa < 1 || numeroEtapa > _stepWidgets.Count)
        {
            return;
        }

        StepRowWidgets alvo = _stepWidgets[numeroEtapa - 1];
        _lblPassoBadge.Text = $"PASSO {alvo.Definicao.Numero} DE {_stepWidgets.Count} • GUIA DIDÁTICO";
        _lblTituloExplicacao.Text = alvo.Definicao.Titulo;
        _lblDescricaoUx.Text = alvo.Definicao.DescricaoUx;

        foreach (StepRowWidgets row in _stepWidgets)
        {
            bool ehAtual = row.Definicao.Numero == numeroEtapa;
            if (ehAtual)
            {
                row.AtualizarVisual(statusAtual, destaqueAtivo: true);
            }
            else if (row.StatusAtual == StatusEtapa.EmAndamento)
            {
                row.AtualizarVisual(StatusEtapa.Concluida, destaqueAtivo: false);
            }
            else
            {
                row.AtualizarVisual(row.StatusAtual, destaqueAtivo: false);
            }
        }
    }

    private void ResetarEstadoVisualEtapas()
    {
        _progressBar.Value = 0;
        _lblPercentual.Text = "0%";
        _lblStatusEtapa.ForeColor = Color.White;
        _lblStatusEtapa.Text = "⏳ Preparando ambiente de implantação...";

        foreach (StepRowWidgets row in _stepWidgets)
        {
            row.AtualizarVisual(StatusEtapa.Pendente, destaqueAtivo: false);
        }

        SelecionarEtapaPreview(1, StatusEtapa.EmAndamento);
    }

    private void AlternarEstadoControlesDuranteExecucao(bool emExecucao)
    {
        _txtApiKey.Enabled = !emExecucao;
        _txtDiretorio.Enabled = !emExecucao;
        _btnProcurar.Enabled = !emExecucao;
        _txtSqlHost.Enabled = !emExecucao;
        _txtSqlBanco.Enabled = !emExecucao;
        _txtSqlUsuario.Enabled = !emExecucao;
        _txtSqlSenha.Enabled = !emExecucao;
        _txtSupersetSenha.Enabled = !emExecucao;

        // Mantém Enabled = true para não esmaecer ou ocultar o checkmark no tema escuro,
        // mas trava o AutoCheck para que o usuário não altere o estado durante a instalação.
        _chkAtalhoDesktop.AutoCheck = !emExecucao;
        _chkFirewall.AutoCheck = !emExecucao;

        _btnInstalar.Enabled = !emExecucao;
        _btnInstalar.Text = emExecucao ? "Instalando..." : "Iniciar Instalação";
        _btnCancelar.Enabled = emExecucao;
    }

    private void RegistrarMensagemInicialConsole()
    {
        AnexarLinhaColorida(
            NivelLog.Info,
            "Bem-vindo ao Advice Installer 2.0 — Instalador Unificado do Dashboard Movidesk BI.");
        AnexarLinhaColorida(
            NivelLog.Info,
            "1) Informe sua Chave da API do Movidesk e escolha o diretório de instalação.");
        AnexarLinhaColorida(
            NivelLog.Info,
            "2) Clique em 'Iniciar Instalação' ou selecione um passo à esquerda para ler o que cada etapa executa.");
    }

    private void RegistrarLogNoConsoleSafe(NivelLog nivel, string linha)
    {
        if (IsDisposed || Disposing)
        {
            return;
        }

        if (InvokeRequired)
        {
            try
            {
                BeginInvoke(() => AnexarLinhaColorida(nivel, linha));
            }
            catch
            {
                // Ignora caso o handle já esteja em encerramento
            }
            return;
        }

        AnexarLinhaColorida(nivel, linha);
    }

    private void AnexarLinhaColorida(NivelLog nivel, string texto)
    {
        if (_rtbLog.IsDisposed || _rtbLog.Disposing)
        {
            return;
        }

        Color cor = nivel switch
        {
            NivelLog.Sucesso => Color.FromArgb(52, 211, 153),
            NivelLog.Erro => Color.FromArgb(248, 113, 113),
            NivelLog.Aguardando => Color.FromArgb(56, 189, 248),
            NivelLog.Aviso => Color.FromArgb(251, 191, 36),
            NivelLog.Comando => Color.FromArgb(132, 165, 194),
            _ => Color.FromArgb(220, 234, 246)
        };

        if (_rtbLog.TextLength > 180_000)
        {
            _rtbLog.Select(0, 45_000);
            _rtbLog.SelectedText = string.Empty;
        }

        _rtbLog.SelectionStart = _rtbLog.TextLength;
        _rtbLog.SelectionLength = 0;
        _rtbLog.SelectionColor = cor;
        _rtbLog.AppendText(texto + Environment.NewLine);
        _rtbLog.SelectionColor = _rtbLog.ForeColor;
        _rtbLog.ScrollToCaret();
    }

    private void AbrirCaminhoSeguro(string caminhoOuUrl)
    {
        if (string.IsNullOrWhiteSpace(caminhoOuUrl))
        {
            return;
        }

        try
        {
            Process.Start(new ProcessStartInfo(caminhoOuUrl) { UseShellExecute = true });
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                this,
                $"Não foi possível abrir '{caminhoOuUrl}':\n{ex.Message}",
                "Aviso",
                MessageBoxButtons.OK,
                MessageBoxIcon.Warning);
        }
    }

    private async void BtnCopiarLog_Click(object? sender, EventArgs e)
    {
        string corpoLog = _rtbLog.Text;

        if (!string.IsNullOrWhiteSpace(_ultimoArquivoLog) && File.Exists(_ultimoArquivoLog))
        {
            try
            {
                using var fs = new FileStream(_ultimoArquivoLog, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
                using var sr = new StreamReader(fs, Encoding.UTF8);
                string arquivoCompleto = sr.ReadToEnd();
                if (!string.IsNullOrWhiteSpace(arquivoCompleto))
                {
                    corpoLog = arquivoCompleto;
                }
            }
            catch
            {
                // Fallback transparente para o conteúdo já renderizado no RichTextBox
            }
        }

        if (string.IsNullOrWhiteSpace(corpoLog))
        {
            MessageBox.Show(
                this,
                "Ainda não há registros de log disponíveis para cópia.",
                "Copiar Log — Dashboard Movidesk BI",
                MessageBoxButtons.OK,
                MessageBoxIcon.Information);
            return;
        }

        string normalizado = corpoLog
            .Replace("\r\n", "\n", StringComparison.Ordinal)
            .Replace("\r", "\n", StringComparison.Ordinal)
            .Replace("\n", Environment.NewLine, StringComparison.Ordinal)
            .TrimEnd();

        var sb = new StringBuilder();
        if (!normalizado.Contains("ADVICE INSTALLER 2.0", StringComparison.Ordinal))
        {
            sb.AppendLine("=== Advice Installer 2.0 — Log Dashboard Movidesk BI ===");
            if (!string.IsNullOrWhiteSpace(_ultimoArquivoLog))
            {
                sb.AppendLine($"Arquivo: {_ultimoArquivoLog}");
            }
            sb.AppendLine($"Copiado em: {DateTime.Now:dd/MM/yyyy HH:mm:ss}");
            sb.AppendLine(new string('-', 60));
        }
        sb.AppendLine(normalizado);

        try
        {
            Clipboard.SetDataObject(sb.ToString(), copy: true, retryTimes: 5, retryDelay: 60);
            _btnCopiarLog.Text = "Copiado ✔";
            await Task.Delay(1800);
            if (!IsDisposed && !_btnCopiarLog.IsDisposed)
            {
                _btnCopiarLog.Text = "Copiar Log";
            }
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                this,
                $"Não foi possível acessar a área de transferência do Windows:\n{ex.Message}",
                "Copiar Log",
                MessageBoxButtons.OK,
                MessageBoxIcon.Warning);
        }
    }

    private static string FormatarMensagemDialogoErro(string? mensagemOriginal, int maxLinhas = 16, int maxCaracteres = 1350)
    {
        if (string.IsNullOrWhiteSpace(mensagemOriginal))
        {
            return "Erro sem descrição detalhada. Consulte o arquivo de log completo.";
        }

        string[] linhas = mensagemOriginal
            .Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries)
            .Select(l => l.Trim())
            .Where(l => !string.IsNullOrWhiteSpace(l))
            .ToArray();

        if (linhas.Length == 0)
        {
            return "Erro sem descrição detalhada. Consulte o arquivo de log completo.";
        }

        int omitidas = Math.Max(0, linhas.Length - maxLinhas);
        IEnumerable<string> cauda = omitidas > 0 ? linhas.Skip(omitidas) : linhas;

        var sb = new StringBuilder();
        if (omitidas > 0)
        {
            sb.AppendLine($"[... {omitidas} linha(s) anteriores omitida(s); consulte o log completo ...]");
        }

        foreach (string linha in cauda)
        {
            sb.AppendLine(linha);
        }

        string texto = sb.ToString().Trim();
        if (texto.Length > maxCaracteres)
        {
            string slice = texto[^maxCaracteres..];
            int firstNewLine = slice.IndexOf('\n');
            if (firstNewLine >= 0 && firstNewLine < slice.Length - 1)
            {
                slice = slice[(firstNewLine + 1)..];
            }

            texto = "[... início omitido; consulte o log completo ...]\n" + slice.TrimStart();
        }

        return texto;
    }

    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        if (_instalacaoEmAndamento)
        {
            DialogResult resp = MessageBox.Show(
                this,
                "Uma implantação ainda está em andamento. Deseja cancelar os processos e fechar o instalador?",
                "Instalação em Andamento",
                MessageBoxButtons.YesNo,
                MessageBoxIcon.Warning);

            if (resp != DialogResult.Yes)
            {
                e.Cancel = true;
                return;
            }

            _cts?.Cancel();
        }

        base.OnFormClosing(e);
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            if (_auditorLog is not null)
            {
                _auditorLog.OnLogEmitido -= RegistrarLogNoConsoleSafe;
                _auditorLog.Dispose();
                _auditorLog = null;
            }

            _cts?.Dispose();
            _cts = null;

            _bgImage?.Dispose();
            _appIcon?.Dispose();
        }

        base.Dispose(disposing);
    }

    private static Panel CriarCardPainel(Color fundo, Color borda)
    {
        var panel = new Panel
        {
            Dock = DockStyle.Fill,
            BackColor = fundo,
            Margin = new Padding(0, 4, 0, 4)
        };
        panel.Paint += (_, e) =>
        {
            if (panel.Width <= 1 || panel.Height <= 1)
            {
                return;
            }
            using var pen = new Pen(borda, 1f);
            var rect = new Rectangle(0, 0, panel.Width - 1, panel.Height - 1);
            e.Graphics.DrawRectangle(pen, rect);
        };
        return panel;
    }

    private static Label CriarLabelCampo(string texto) => new()
    {
        Text = texto,
        ForeColor = CorTextoSecundario,
        Font = new Font("Segoe UI", 8f, FontStyle.Bold),
        Dock = DockStyle.Fill,
        TextAlign = ContentAlignment.BottomLeft
    };

    private static TextBox CriarTextBoxEstilizado(
        string textoInicial,
        string placeholder,
        bool ocultarSenha = false) => new()
    {
        Text = textoInicial,
        PlaceholderText = placeholder,
        UseSystemPasswordChar = ocultarSenha,
        Dock = DockStyle.Fill,
        BorderStyle = BorderStyle.FixedSingle,
        BackColor = Color.FromArgb(6, 17, 30),
        ForeColor = Color.White,
        Font = new Font("Segoe UI", 9.2f, FontStyle.Regular)
    };

    private static Button CriarBotaoSecundario(string texto, int width)
    {
        var btn = new Button
        {
            Text = texto,
            Width = width,
            Height = 28,
            FlatStyle = FlatStyle.Flat,
            BackColor = CorAzulAdvice,
            ForeColor = Color.White,
            Font = new Font("Segoe UI", 8.8f, FontStyle.Bold),
            Cursor = Cursors.Hand
        };
        btn.FlatAppearance.BorderColor = CorBordaSutil;
        btn.FlatAppearance.BorderSize = 1;
        return btn;
    }

    private sealed class StepRowWidgets
    {
        private static readonly Font FontePassoNormal = new("Segoe UI", 9f, FontStyle.Regular);
        private static readonly Font FontePassoDestaque = new("Segoe UI", 9f, FontStyle.Bold);

        public EtapaDefinicao Definicao { get; }
        public Panel Container { get; }
        private readonly Panel _accentBar;
        private readonly Label _lblIcone;
        private readonly Label _lblTexto;
        public StatusEtapa StatusAtual { get; private set; } = StatusEtapa.Pendente;

        public StepRowWidgets(
            EtapaDefinicao definicao,
            Panel container,
            Panel accentBar,
            Label lblIcone,
            Label lblTexto)
        {
            Definicao = definicao;
            Container = container;
            _accentBar = accentBar;
            _lblIcone = lblIcone;
            _lblTexto = lblTexto;
        }

        public void AtualizarVisual(StatusEtapa status, bool destaqueAtivo)
        {
            StatusAtual = status;

            (string simbolo, Color corSimbolo) = status switch
            {
                StatusEtapa.EmAndamento => ("⏳", CorCianoBrilho),
                StatusEtapa.Concluida => ("✔", Color.FromArgb(52, 211, 153)),
                StatusEtapa.Aviso => ("⚠", Color.FromArgb(251, 191, 36)),
                StatusEtapa.Erro => ("❌", Color.FromArgb(248, 113, 113)),
                _ => ("○", destaqueAtivo ? CorDouradoAdvice : CorTextoSecundario)
            };

            _lblIcone.Text = simbolo;
            _lblIcone.ForeColor = corSimbolo;

            Container.BackColor = destaqueAtivo
                ? CorCardAtivo
                : Color.FromArgb(12, 30, 49);

            _accentBar.BackColor = destaqueAtivo
                ? CorDouradoAdvice
                : status == StatusEtapa.Concluida
                    ? Color.FromArgb(52, 211, 153)
                    : Color.Transparent;

            _lblTexto.ForeColor = destaqueAtivo || status == StatusEtapa.EmAndamento
                ? Color.White
                : status == StatusEtapa.Concluida
                    ? Color.FromArgb(215, 245, 232)
                    : CorTextoSecundario;

            _lblTexto.Font = destaqueAtivo || status == StatusEtapa.EmAndamento
                ? FontePassoDestaque
                : FontePassoNormal;
        }
    }

    private sealed class AdviceProgressBar : Control
    {
        private int _value;

        public int Value
        {
            get => _value;
            set
            {
                int clamped = Math.Clamp(value, 0, 100);
                if (_value != clamped)
                {
                    _value = clamped;
                    Invalidate();
                }
            }
        }

        public AdviceProgressBar()
        {
            SetStyle(
                ControlStyles.AllPaintingInWmPaint |
                ControlStyles.UserPaint |
                ControlStyles.OptimizedDoubleBuffer |
                ControlStyles.ResizeRedraw,
                true);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            if (ClientSize.Width <= 1 || ClientSize.Height <= 1)
            {
                return;
            }

            e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
            using (var trackBrush = new SolidBrush(Color.FromArgb(15, 42, 68)))
            {
                e.Graphics.FillRectangle(trackBrush, ClientRectangle);
            }

            if (_value > 0 && ClientSize.Width > 2)
            {
                int fillWidth = Math.Max(4, (int)Math.Round(ClientSize.Width * (_value / 100.0)));
                var fillRect = new Rectangle(0, 0, fillWidth, ClientSize.Height);
                using var fillBrush = new LinearGradientBrush(
                    fillRect,
                    CorCianoBrilho,
                    CorDouradoAdvice,
                    LinearGradientMode.Horizontal);
                e.Graphics.FillRectangle(fillBrush, fillRect);
            }

            using var borderPen = new Pen(CorBordaSutil, 1f);
            e.Graphics.DrawRectangle(borderPen, 0, 0, ClientSize.Width - 1, ClientSize.Height - 1);
        }
    }
}
