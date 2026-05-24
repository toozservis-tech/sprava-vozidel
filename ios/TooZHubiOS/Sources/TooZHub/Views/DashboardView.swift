import Charts
import SwiftUI

struct DashboardView: View {
    @EnvironmentObject private var env: AppEnvironment
    @EnvironmentObject private var viewModel: DashboardViewModel
    @AppStorage("dashboard.didDismissWelcomeExperience") private var didDismissWelcomeExperience = false
    @AppStorage("dashboard.showWelcomeDeck") private var showWelcomeDeck = true
    @AppStorage("dashboard.showWorkspaceDeck") private var showWorkspaceDeck = true
    @AppStorage("dashboard.showQuickActions") private var showQuickActions = true
    @AppStorage("dashboard.showVehiclesOverview") private var showVehiclesOverview = true
    @AppStorage("dashboard.showRemindersOverview") private var showRemindersOverview = true
    @AppStorage("dashboard.showNotificationsOverview") private var showNotificationsOverview = true
    @AppStorage("dashboard.showCostChart") private var showCostChart = true
    @AppStorage("dashboard.compactMode") private var compactMode = false
    @AppStorage("dashboard.highlightMode") private var highlightModeRaw = DashboardHighlightMode.balanced.rawValue
    @AppStorage("dashboard.moduleOrder") private var moduleOrderRaw = DashboardModule.defaultStorageValue
    @State private var isPresentingCustomization = false
    @State private var selectedVehicleForDetail: Vehicle?

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: dashboardSpacing) {
                    if viewModel.isLoading {
                        ProgressView()
                            .tint(.white)
                            .frame(maxWidth: .infinity)
                            .padding(.top, 40)
                    } else if let error = viewModel.error {
                        ErrorStateView(message: error) {
                            Task { await reload() }
                        }
                    } else {
                        if showWelcomeDeck {
                            welcomeDeckSection
                        }
                        ForEach(orderedModules) { module in
                            moduleSection(module)
                        }
                    }
                }
                .padding(.horizontal, Theme.Spacing.md)
                .padding(.top, Theme.Spacing.md)
                .padding(.bottom, 168)
            }
            .hubPageBackground()
            .navigationTitle("Dashboard")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbarBackground(.hidden, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        isPresentingCustomization = true
                    } label: {
                        Image(systemName: "slider.horizontal.3")
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundStyle(.white)
                            .frame(width: 38, height: 38)
                            .background(Theme.Colors.elevated.opacity(0.92), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                            .overlay(
                                RoundedRectangle(cornerRadius: 14, style: .continuous)
                                    .stroke(Theme.Colors.hairline, lineWidth: 1)
                            )
                    }
                    .buttonStyle(.plain)
                }
            }
            .task { await reload() }
            .refreshable { await reload(force: true) }
            .sheet(isPresented: $isPresentingCustomization) {
                DashboardCustomizationSheet(
                    showWelcomeDeck: $showWelcomeDeck,
                    compactMode: $compactMode,
                    highlightModeRaw: $highlightModeRaw,
                    moduleOrderRaw: $moduleOrderRaw,
                    visibleModules: visibleModuleBindings
                )
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
            }
            .sheet(item: $selectedVehicleForDetail) { vehicle in
                NavigationStack {
                    VehicleDetailView(vehicleId: vehicle.id)
                }
            }
            .fullScreenCover(isPresented: welcomeExperienceBinding) {
                DashboardWelcomeExperienceView {
                    didDismissWelcomeExperience = true
                }
            }
        }
    }

    private var dashboardSpacing: CGFloat {
        compactMode ? Theme.Spacing.md : Theme.Spacing.lg
    }

    private var highlightMode: DashboardHighlightMode {
        DashboardHighlightMode(rawValue: highlightModeRaw) ?? .balanced
    }

    private var orderedModules: [DashboardModule] {
        DashboardModule.modules(
            from: moduleOrderRaw,
            visible: visibleModules
        )
    }

    private var visibleModules: Set<DashboardModule> {
        var result = Set<DashboardModule>()
        if showWorkspaceDeck { result.insert(.workspace) }
        result.insert(.stats)
        if showQuickActions { result.insert(.quickActions) }
        if showVehiclesOverview { result.insert(.vehicles) }
        if showRemindersOverview { result.insert(.reminders) }
        if showNotificationsOverview { result.insert(.notifications) }
        if showCostChart { result.insert(.costs) }
        return result
    }

    private var visibleModuleBindings: [DashboardModule: Binding<Bool>] {
        [
            .workspace: $showWorkspaceDeck,
            .stats: .constant(true),
            .quickActions: $showQuickActions,
            .vehicles: $showVehiclesOverview,
            .reminders: $showRemindersOverview,
            .notifications: $showNotificationsOverview,
            .costs: $showCostChart
        ]
    }

    private var welcomeExperienceBinding: Binding<Bool> {
        Binding(
            get: { !didDismissWelcomeExperience },
            set: { newValue in
                if !newValue {
                    didDismissWelcomeExperience = true
                }
            }
        )
    }

    @ViewBuilder
    private func moduleSection(_ module: DashboardModule) -> some View {
        switch module {
        case .workspace:
            topOverviewSection
        case .stats:
            cardsSection
        case .quickActions:
            quickActionsSection
        case .vehicles:
            vehiclesOverview
        case .reminders:
            remindersOverview
        case .notifications:
            notificationsOverview
        case .costs:
            chartSection
        }
    }

    private var welcomeDeckSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.md) {
            HStack(alignment: .top, spacing: Theme.Spacing.md) {
                VStack(alignment: .leading, spacing: 8) {
                    Text(greetingTitle)
                        .font(.system(size: 24, weight: .bold))
                        .foregroundStyle(.white)
                        .lineLimit(2)
                        .minimumScaleFactor(0.85)
                    Text(greetingSubtitle)
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colors.textSecondary)
                        .lineLimit(3)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: Theme.Spacing.sm)
                VStack(alignment: .trailing, spacing: 10) {
                    statusBadge(
                        title: serverStatusLabel,
                        tint: serverStatusColor,
                        icon: serverStatusIcon
                    )
                    Button("Přizpůsobit plochu") {
                        isPresentingCustomization = true
                    }
                    .font(Theme.Typography.tiny)
                    .foregroundStyle(.white)
                    .padding(.horizontal, Theme.Spacing.sm)
                    .padding(.vertical, 7)
                    .background(Theme.Colors.elevated.opacity(0.9), in: Capsule())
                    .overlay(
                        Capsule()
                            .stroke(Theme.Colors.hairline.opacity(0.8), lineWidth: 1)
                    )
                    .buttonStyle(.plain)
                }
            }

            HStack(spacing: Theme.Spacing.xs) {
                welcomeMetricPill(icon: "car.fill", title: "Vozový park", value: "\(viewModel.vehicles.count)")
                welcomeMetricPill(icon: "wrench.and.screwdriver.fill", title: "Aktivní servis", value: "\(pendingReminderCount)")
                welcomeMetricPill(icon: "banknote.fill", title: "Náklady", value: formatCompactCurrency(viewModel.analytics?.totalCostCzk ?? 0))
            }

            HStack(spacing: Theme.Spacing.sm) {
                heroActionButton(
                    title: "Pokračovat ve vozidlech",
                    subtitle: "Garáž a detail",
                    icon: "car.circle.fill",
                    tint: Theme.Colors.primary
                ) {
                    env.requestedUserTab = "vehicles"
                }

                heroActionButton(
                    title: "Nový záznam",
                    subtitle: "Servis nebo doklad",
                    icon: "plus.circle.fill",
                    tint: Theme.Colors.accent
                ) {
                    env.requestedUserTab = "service"
                }
            }
        }
        .padding(Theme.Spacing.md)
        .background(
            RoundedRectangle(cornerRadius: Theme.Radius.xl, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [
                            Theme.Colors.surface.opacity(0.96),
                            Theme.Colors.elevated.opacity(0.92),
                            Theme.Colors.primaryDark.opacity(0.75)
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
        )
        .overlay(
            RoundedRectangle(cornerRadius: Theme.Radius.xl, style: .continuous)
                .stroke(Theme.Colors.hairline.opacity(0.9), lineWidth: 1)
        )
        .shadow(color: Theme.Shadow.medium, radius: 14, y: 8)
    }

    private var topOverviewSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
            HStack(spacing: Theme.Spacing.sm) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Vaše plocha")
                        .font(Theme.Typography.captionStrong)
                        .foregroundStyle(Theme.Colors.textSecondary)
                    Text(highlightMode.title)
                        .font(Theme.Typography.cardTitle)
                        .foregroundStyle(.white)
                }
                Spacer()
                Menu {
                    ForEach(DashboardHighlightMode.allCases) { mode in
                        Button {
                            highlightModeRaw = mode.rawValue
                        } label: {
                            Label(mode.title, systemImage: mode.iconName)
                        }
                    }
                } label: {
                    Label("Režim", systemImage: "sparkles.rectangle.stack")
                        .font(Theme.Typography.tiny)
                        .foregroundStyle(.white)
                        .padding(.horizontal, Theme.Spacing.sm)
                        .padding(.vertical, 7)
                        .background(Theme.Colors.elevated.opacity(0.92), in: Capsule())
                        .overlay(
                            Capsule()
                                .stroke(Theme.Colors.hairline, lineWidth: 1)
                        )
                }
                .buttonStyle(.plain)
            }

            Text(highlightMode.subtitle)
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colors.textSecondary)

            if compactMode {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: Theme.Spacing.xs) {
                        ForEach(workspaceCards) { card in
                            workspaceCard(card)
                                .frame(width: 230)
                        }
                    }
                    .padding(.horizontal, 1)
                }
            } else {
                VStack(spacing: Theme.Spacing.xs) {
                    ForEach(Array(workspaceCards.chunked(into: 2).enumerated()), id: \.offset) { _, row in
                        HStack(spacing: Theme.Spacing.xs) {
                            ForEach(row) { card in
                                workspaceCard(card)
                            }
                        }
                    }
                }
            }
        }
        .padding(Theme.Spacing.md)
        .background(
            RoundedRectangle(cornerRadius: Theme.Radius.xl, style: .continuous)
                .fill(Theme.Colors.surface.opacity(0.88))
        )
        .overlay(
            RoundedRectangle(cornerRadius: Theme.Radius.xl, style: .continuous)
                .stroke(Theme.Colors.hairline, lineWidth: 1)
        )
        .shadow(color: Theme.Shadow.medium, radius: 10, y: 6)
    }

    private var nextDateSummaryValue: String {
        if let nearestReminderDate {
            return formattedCompactDate(nearestReminderDate)
        }
        if let latestService = viewModel.analytics?.latestServiceAt {
            return formattedCompactDate(latestService)
        }
        return "Bez termínu"
    }

    private var nextDateIcon: String {
        nearestReminderDate == nil && viewModel.analytics?.latestServiceAt != nil ? "wrench.and.screwdriver.fill" : "calendar"
    }

    private var nearestReminderDate: Date? {
        viewModel.reminders
            .compactMap(\.dueDate)
            .sorted()
            .first
    }

    private func openDateContext() {
        if nearestReminderDate != nil {
            env.requestedUserTab = "reservations"
        } else if viewModel.analytics?.latestServiceAt != nil {
            env.requestedUserTab = "service"
        } else {
            env.requestedUserTab = "reservations"
        }
    }

    private func formattedCompactDate(_ value: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "cs_CZ")
        formatter.dateFormat = "d. M. yyyy"
        return formatter.string(from: value)
    }

    private func summaryQuickTile(
        icon: String,
        title: String,
        value: String,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 6) {
                Image(systemName: icon)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.Colors.primary)
                    .frame(width: 24, height: 24)
                    .background(Theme.Colors.primary.opacity(0.16), in: RoundedRectangle(cornerRadius: 8, style: .continuous))

                Text(title)
                    .font(.system(size: 10, weight: .medium))
                    .foregroundStyle(Theme.Colors.textSecondary)
                    .lineLimit(1)
                Text(value)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(.white)
                    .lineLimit(1)
                    .minimumScaleFactor(0.85)
            }
            .frame(maxWidth: .infinity, minHeight: 78, alignment: .leading)
            .padding(.horizontal, Theme.Spacing.sm)
            .padding(.vertical, Theme.Spacing.xs)
            .background(
                RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous)
                    .fill(Theme.Colors.elevated.opacity(0.94))
            )
            .overlay(
                RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous)
                    .stroke(Theme.Colors.hairline.opacity(0.75), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .frame(maxWidth: .infinity)
    }

    private var cardsSection: some View {
        HStack(spacing: Theme.Spacing.sm) {
            StatCard(
                title: "Aktivní vozidla",
                value: "\(viewModel.vehicles.count)",
                subtitle: "Ve vašem účtu",
                icon: "car.fill"
            )

            NavigationLink {
                CostInsightsView()
            } label: {
                StatCard(
                    title: "Celkové náklady",
                    value: "\(Int(viewModel.analytics?.totalCostCzk ?? 0)) Kč",
                    subtitle: "Servis + údržba",
                    icon: "banknote.fill"
                )
            }
            .buttonStyle(.plain)
        }
    }

    private var quickActionsSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
            SectionHeader(title: "Rychlé akce", subtitle: compactMode ? "Minimalistické zkratky" : "Nejrychlejší vstupy do práce")

            LazyVGrid(
                columns: Array(repeating: GridItem(.flexible(), spacing: Theme.Spacing.xs), count: compactMode ? 4 : 2),
                spacing: Theme.Spacing.xs
            ) {
                QuickActionCompactTile(
                    icon: "car.fill",
                    title: "Vozidla",
                    subtitle: "Seznam",
                    tint: Theme.Colors.primary
                ) {
                    env.requestedUserTab = "vehicles"
                }
                QuickActionCompactTile(
                    icon: "wrench.and.screwdriver",
                    title: "Servis",
                    subtitle: "Záznamy",
                    tint: Theme.Colors.accent
                ) {
                    env.requestedUserTab = "service"
                }
                QuickActionCompactTile(
                    icon: "calendar.badge.plus",
                    title: "Rezervace",
                    subtitle: "Termíny",
                    tint: Theme.Colors.warning
                ) {
                    env.requestedUserTab = "reservations"
                }
                QuickActionCompactTile(
                    icon: "person.crop.circle",
                    title: "Profil",
                    subtitle: "Účet",
                    tint: Theme.Colors.primaryDark
                ) {
                    env.requestedUserTab = "account"
                }
            }
            .padding(Theme.Spacing.xs)
            .background(
                RoundedRectangle(cornerRadius: Theme.Radius.lg, style: .continuous)
                    .fill(Theme.Colors.lightCard)
            )
            .overlay(
                RoundedRectangle(cornerRadius: Theme.Radius.lg, style: .continuous)
                    .stroke(Theme.Colors.cardHairline.opacity(0.75), lineWidth: 1)
            )
            .shadow(color: Theme.Shadow.soft, radius: 8, y: 4)
        }
    }

    private var vehiclesOverview: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            SectionHeader(title: "Vozidla", subtitle: "Rychlý přístup k detailům")

            if viewModel.vehicles.isEmpty {
                EmptyStateView(
                    icon: "car.rear",
                    title: "Zatím nemáte žádné vozidlo",
                    subtitle: "Přidejte první vozidlo a otevřete si servisní historii.",
                    actionTitle: "Přidat vozidlo"
                ) {
                    env.requestedUserTab = "vehicles"
                }
            } else {
                ForEach(viewModel.vehicles.prefix(compactMode ? 1 : 2)) { vehicle in
                    Button {
                        selectedVehicleForDetail = vehicle
                    } label: {
                        VehicleCard(vehicle: vehicle)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    private var remindersOverview: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            SectionHeader(title: "Servisní připomínky", subtitle: "Co je potřeba vyřešit")

            if viewModel.reminders.isEmpty {
                EmptyStateView(
                    icon: "bell.slash",
                    title: "Bez aktivních upozornění",
                    subtitle: "Všechny servisní úkoly jsou aktuálně splněné."
                )
            } else {
                VStack(spacing: Theme.Spacing.sm) {
                    ForEach(viewModel.reminders.prefix(compactMode ? 3 : 4), id: \.self) { reminder in
                        TimelineRow(
                            title: reminder.text,
                            subtitle: reminder.type,
                            date: reminder.dueDate,
                            color: reminder.isCompleted == true ? Theme.Colors.primary : Theme.Colors.warning
                        )

                        if reminder.id != viewModel.reminders.prefix(compactMode ? 3 : 4).last?.id {
                            Divider()
                                .overlay(Theme.Colors.hairline)
                        }
                    }
                }
                .hubDarkCard()
            }
        }
    }

    private var notificationsOverview: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            SectionHeader(title: "Systémová oznámení", subtitle: "Stav aplikace a účtu")

            if viewModel.notifications.isEmpty {
                EmptyStateView(
                    icon: "checkmark.shield",
                    title: "Žádná nová oznámení",
                    subtitle: "Systém je v pořádku a bez kritických stavů."
                )
            } else {
                VStack(spacing: Theme.Spacing.sm) {
                    ForEach(viewModel.notifications.prefix(compactMode ? 3 : 4)) { item in
                        let color: Color = {
                            switch item.severity.lowercased() {
                            case "critical":
                                return Theme.Colors.danger
                            case "warning":
                                return Theme.Colors.warning
                            default:
                                return Theme.Colors.primary
                            }
                        }()

                        TimelineRow(
                            title: item.title,
                            subtitle: item.message,
                            date: item.createdAt,
                            color: color
                        )

                        if item.id != viewModel.notifications.prefix(compactMode ? 3 : 4).last?.id {
                            Divider()
                                .overlay(Theme.Colors.hairline)
                        }
                    }
                }
                .hubDarkCard()
            }
        }
    }

    private var chartSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            HStack(spacing: Theme.Spacing.sm) {
                Text("Přehled nákladů")
                    .font(Theme.Typography.cardTitle)
                    .foregroundStyle(Theme.Colors.textOnLight)
                Spacer()
                NavigationLink {
                    CostInsightsView()
                } label: {
                    HStack(spacing: 6) {
                        Text("Detail")
                        Image(systemName: "slider.horizontal.3")
                    }
                    .font(Theme.Typography.tiny)
                    .foregroundStyle(Theme.Colors.textOnLight)
                    .padding(.horizontal, Theme.Spacing.sm)
                    .padding(.vertical, 6)
                    .background(Theme.Colors.lightMuted, in: Capsule())
                }
                .buttonStyle(.plain)
            }

            if viewModel.monthlyCosts.isEmpty {
                VStack(spacing: Theme.Spacing.sm) {
                    Image(systemName: "chart.bar.xaxis")
                        .font(.title2)
                        .foregroundStyle(Theme.Colors.textOnLightSecondary)
                    Text("Zatím nemáte data pro graf")
                        .font(Theme.Typography.bodyStrong)
                        .foregroundStyle(Theme.Colors.textOnLight)
                    Text("Po přidání servisních záznamů zde uvidíte vývoj nákladů.")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colors.textOnLightSecondary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, Theme.Spacing.lg)
            } else {
                Chart(viewModel.monthlyCosts) { item in
                    BarMark(
                        x: .value("Měsíc", item.label),
                        y: .value("Náklady", item.totalCostCzk)
                    )
                    .foregroundStyle(
                        LinearGradient(
                            colors: [Theme.Colors.accent, Theme.Colors.primary],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    )
                    .cornerRadius(7)
                }
                .frame(height: 220)
                .chartXAxis {
                    AxisMarks(values: .automatic) { value in
                        AxisValueLabel {
                            if let label = value.as(String.self) {
                                Text(label)
                                    .font(.system(size: 10, weight: .medium))
                                    .foregroundStyle(Theme.Colors.textOnLightSecondary)
                            }
                        }
                    }
                }
                .chartYAxis {
                    AxisMarks(position: .leading) { value in
                        AxisValueLabel {
                            if let amount = value.as(Double.self) {
                                Text("\(Int(amount))")
                                    .font(.system(size: 10, weight: .medium))
                                    .foregroundStyle(Theme.Colors.textOnLightSecondary)
                            }
                        }
                        AxisGridLine(stroke: StrokeStyle(lineWidth: 0.6, dash: [4, 4]))
                            .foregroundStyle(Theme.Colors.cardHairline.opacity(0.65))
                    }
                }
            }
        }
        .hubLightCard()
    }

    private var greetingTitle: String {
        let hour = Calendar.current.component(.hour, from: .now)
        let firstName = env.authManager.user?.name?
            .split(separator: " ")
            .first
            .map(String.init)?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let suffix = firstName.map { ", \($0)" } ?? ""

        switch hour {
        case 5..<12:
            return "Dobré ráno\(suffix)"
        case 12..<18:
            return "Dobrý den\(suffix)"
        default:
            return "Dobrý večer\(suffix)"
        }
    }

    private var greetingSubtitle: String {
        if pendingReminderCount > 0 {
            return "\(pendingReminderCount) aktivních servisních úkolů a \(viewModel.vehicles.count) vozidel připravených k práci."
        }
        return "Plocha je připravená. Upravte si moduly podle toho, co skutečně používáte."
    }

    private var pendingReminderCount: Int {
        viewModel.reminders.filter { $0.isCompleted != true }.count
    }

    private var latestServiceDate: Date? {
        viewModel.analytics?.latestServiceAt
    }

    private var serverStatusLabel: String {
        switch env.serverStatusMonitor.state {
        case .connecting:
            return "Připojování"
        case .online:
            return "Server online"
        case .offline:
            return "Server offline"
        }
    }

    private var serverStatusIcon: String {
        switch env.serverStatusMonitor.state {
        case .connecting:
            return "bolt.horizontal.circle.fill"
        case .online:
            return "checkmark.circle.fill"
        case .offline:
            return "wifi.slash"
        }
    }

    private var serverStatusColor: Color {
        switch env.serverStatusMonitor.state {
        case .connecting:
            return Theme.Colors.warning
        case .online:
            return Theme.Colors.primary
        case .offline:
            return Theme.Colors.danger
        }
    }

    private var workspaceCards: [WorkspaceCardModel] {
        switch highlightMode {
        case .balanced:
            return [
                WorkspaceCardModel(
                    title: "Vozový park",
                    subtitle: "\(viewModel.vehicles.count) aktivních vozidel",
                    value: nextVehicleLabel,
                    icon: "car.2.fill",
                    tint: Theme.Colors.primary,
                    action: { env.requestedUserTab = "vehicles" }
                ),
                WorkspaceCardModel(
                    title: "Servisní pozornost",
                    subtitle: pendingReminderCount == 0 ? "Bez otevřených úkolů" : "\(pendingReminderCount) otevřených připomínek",
                    value: nextDateSummaryValue,
                    icon: "wrench.and.screwdriver.fill",
                    tint: Theme.Colors.accent,
                    action: { env.requestedUserTab = "service" }
                ),
                WorkspaceCardModel(
                    title: "Rezervace",
                    subtitle: nearestReminderDate == nil ? "Bez naplánovaného termínu" : "Další termín",
                    value: nextDateSummaryValue,
                    icon: "calendar.badge.clock",
                    tint: Theme.Colors.warning,
                    action: { env.requestedUserTab = "reservations" }
                ),
                WorkspaceCardModel(
                    title: "Nákladový přehled",
                    subtitle: "Celkové servisní výdaje",
                    value: formatCompactCurrency(viewModel.analytics?.totalCostCzk ?? 0),
                    icon: "banknote.fill",
                    tint: Theme.Colors.primaryDark,
                    action: { env.requestedUserTab = "dashboard" }
                )
            ]
        case .garage:
            return [
                WorkspaceCardModel(
                    title: "Rychlý vstup do vozidel",
                    subtitle: "Detail, technika a historie",
                    value: nextVehicleLabel,
                    icon: "car.fill",
                    tint: Theme.Colors.primary,
                    action: { env.requestedUserTab = "vehicles" }
                ),
                WorkspaceCardModel(
                    title: "Další přidání",
                    subtitle: "Nové vozidlo nebo úprava garáže",
                    value: "Správa flotily",
                    icon: "plus.circle.fill",
                    tint: Theme.Colors.accent,
                    action: { env.requestedUserTab = "vehicles" }
                )
            ]
        case .service:
            return [
                WorkspaceCardModel(
                    title: "Servisní centrum",
                    subtitle: pendingReminderCount == 0 ? "Žádné urgentní zásahy" : "Zkontrolujte prioritu úkolů",
                    value: pendingReminderCount == 0 ? "Klidový stav" : "\(pendingReminderCount) úkolů",
                    icon: "wrench.and.screwdriver.fill",
                    tint: Theme.Colors.accent,
                    action: { env.requestedUserTab = "service" }
                ),
                WorkspaceCardModel(
                    title: "Poslední servis",
                    subtitle: latestServiceDate == nil ? "Zatím bez záznamu" : "Nejnovější uzavřený zásah",
                    value: latestServiceDate.map(formattedCompactDate) ?? "Bez dat",
                    icon: "clock.arrow.circlepath",
                    tint: Theme.Colors.warning,
                    action: { env.requestedUserTab = "service" }
                ),
                WorkspaceCardModel(
                    title: "Nový záznam",
                    subtitle: "Ruční, sken nebo šablona",
                    value: "Přidat servis",
                    icon: "doc.badge.plus",
                    tint: Theme.Colors.primaryDark,
                    action: { env.requestedUserTab = "service" }
                )
            ]
        case .costs:
            return [
                WorkspaceCardModel(
                    title: "Celkové náklady",
                    subtitle: "Servis + údržba",
                    value: formatCompactCurrency(viewModel.analytics?.totalCostCzk ?? 0),
                    icon: "banknote.fill",
                    tint: Theme.Colors.warning,
                    action: { env.requestedUserTab = "dashboard" }
                ),
                WorkspaceCardModel(
                    title: "Vývoj za měsíc",
                    subtitle: latestMonthCostLabel,
                    value: latestMonthCostValue,
                    icon: "chart.bar.fill",
                    tint: Theme.Colors.primary,
                    action: { env.requestedUserTab = "dashboard" }
                ),
                WorkspaceCardModel(
                    title: "Otevřít detail",
                    subtitle: "Filtrovaný cost insight",
                    value: "Přehled nákladů",
                    icon: "slider.horizontal.3",
                    tint: Theme.Colors.accent,
                    action: { env.requestedUserTab = "dashboard" }
                )
            ]
        }
    }

    private var nextVehicleLabel: String {
        viewModel.vehicles.first?.displayName ?? "Bez vozidla"
    }

    private var latestMonthCostLabel: String {
        viewModel.monthlyCosts.last?.label ?? "Bez měsíčních dat"
    }

    private var latestMonthCostValue: String {
        formatCompactCurrency(viewModel.monthlyCosts.last?.totalCostCzk ?? 0)
    }

    private func formatCompactCurrency(_ value: Double) -> String {
        let number = Int(value.rounded())
        let formatter = NumberFormatter()
        formatter.locale = Locale(identifier: "cs_CZ")
        formatter.numberStyle = .decimal
        let text = formatter.string(from: NSNumber(value: number)) ?? "\(number)"
        return "\(text) Kč"
    }

    private func welcomeMetricPill(icon: String, title: String, value: String) -> some View {
        HStack(spacing: 8) {
            Image(systemName: icon)
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(Theme.Colors.primary)
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.system(size: 10, weight: .medium))
                    .foregroundStyle(Theme.Colors.textSecondary)
                Text(value)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(.white)
                    .lineLimit(1)
            }
        }
        .padding(.horizontal, Theme.Spacing.sm)
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity, minHeight: 52, alignment: .leading)
        .background(Theme.Colors.elevated.opacity(0.88), in: Capsule())
        .overlay(
            Capsule()
                .stroke(Theme.Colors.hairline.opacity(0.8), lineWidth: 1)
        )
    }

    private func statusBadge(title: String, tint: Color, icon: String) -> some View {
        HStack(spacing: 8) {
            Circle()
                .fill(tint)
                .frame(width: 9, height: 9)
            Text(title)
                .font(Theme.Typography.tiny)
                .foregroundStyle(.white)
            Image(systemName: icon)
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(tint)
        }
        .padding(.horizontal, Theme.Spacing.sm)
        .padding(.vertical, 8)
        .background(Theme.Colors.elevated.opacity(0.9), in: Capsule())
        .overlay(
            Capsule()
                .stroke(Theme.Colors.hairline.opacity(0.8), lineWidth: 1)
        )
    }

    private func heroActionButton(
        title: String,
        subtitle: String,
        icon: String,
        tint: Color,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                HStack(spacing: Theme.Spacing.sm) {
                    Image(systemName: icon)
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundStyle(tint)
                        .frame(width: 38, height: 38)
                        .background(tint.opacity(0.16), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    Spacer(minLength: 0)
                    Image(systemName: "arrow.up.right")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundStyle(.white.opacity(0.75))
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text(title)
                        .font(Theme.Typography.bodyStrong)
                        .foregroundStyle(.white)
                        .multilineTextAlignment(.leading)
                        .lineLimit(2)
                        .minimumScaleFactor(0.82)
                    Text(subtitle)
                        .font(Theme.Typography.tiny)
                        .foregroundStyle(Theme.Colors.textSecondary)
                        .multilineTextAlignment(.leading)
                        .lineLimit(2)
                }
            }
            .padding(Theme.Spacing.sm)
            .frame(maxWidth: .infinity, minHeight: 116, alignment: .topLeading)
            .background(Theme.Colors.elevated.opacity(0.92), in: RoundedRectangle(cornerRadius: Theme.Radius.lg, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: Theme.Radius.lg, style: .continuous)
                    .stroke(Theme.Colors.hairline.opacity(0.8), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }

    private func workspaceCard(_ card: WorkspaceCardModel) -> some View {
        Button(action: card.action) {
            VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                HStack {
                    Image(systemName: card.icon)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(card.tint)
                        .frame(width: 30, height: 30)
                        .background(card.tint.opacity(0.16), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                    Spacer()
                    Image(systemName: "chevron.right")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(.white.opacity(0.5))
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text(card.title)
                        .font(Theme.Typography.bodyStrong)
                        .foregroundStyle(.white)
                        .multilineTextAlignment(.leading)
                        .lineLimit(2)
                        .minimumScaleFactor(0.82)
                    Text(card.subtitle)
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colors.textSecondary)
                        .multilineTextAlignment(.leading)
                        .lineLimit(3)
                    Text(card.value)
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(card.tint)
                        .lineLimit(1)
                        .minimumScaleFactor(0.85)
                        .multilineTextAlignment(.leading)
                }
            }
            .frame(maxWidth: .infinity, minHeight: compactMode ? 120 : 132, alignment: .topLeading)
            .padding(Theme.Spacing.sm)
            .background(
                RoundedRectangle(cornerRadius: Theme.Radius.lg, style: .continuous)
                    .fill(Theme.Colors.elevated.opacity(0.94))
            )
            .overlay(
                RoundedRectangle(cornerRadius: Theme.Radius.lg, style: .continuous)
                    .stroke(Theme.Colors.hairline.opacity(0.75), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }

    private func reload(force: Bool = false) async {
        guard let token = env.authManager.token else { return }
        await viewModel.loadIfNeeded(token: token, force: force)
    }
}

private struct WorkspaceCardModel: Identifiable {
    let id = UUID()
    let title: String
    let subtitle: String
    let value: String
    let icon: String
    let tint: Color
    let action: () -> Void
}

private enum DashboardModule: String, CaseIterable, Identifiable {
    case workspace
    case stats
    case quickActions
    case vehicles
    case reminders
    case notifications
    case costs

    var id: String { rawValue }

    static var defaultOrder: [DashboardModule] {
        [.workspace, .stats, .quickActions, .vehicles, .reminders, .notifications, .costs]
    }

    static var defaultStorageValue: String {
        defaultOrder.map(\.rawValue).joined(separator: ",")
    }

    static func modules(from rawValue: String, visible: Set<DashboardModule>) -> [DashboardModule] {
        let parsed = rawValue
            .split(separator: ",")
            .compactMap { DashboardModule(rawValue: String($0)) }

        let ordered = (parsed.isEmpty ? defaultOrder : parsed) + defaultOrder
        var seen = Set<DashboardModule>()

        return ordered.compactMap { module in
            guard visible.contains(module), seen.insert(module).inserted else { return nil }
            return module
        }
    }

    var title: String {
        switch self {
        case .workspace:
            return "Pracovní plocha"
        case .stats:
            return "Souhrnné karty"
        case .quickActions:
            return "Rychlé akce"
        case .vehicles:
            return "Vozidla"
        case .reminders:
            return "Připomínky"
        case .notifications:
            return "Oznámení"
        case .costs:
            return "Graf nákladů"
        }
    }

    var subtitle: String {
        switch self {
        case .workspace:
            return "Horní pracovní cockpit"
        case .stats:
            return "Dvě hlavní KPI karty"
        case .quickActions:
            return "Nejrychlejší vstupy do funkcí"
        case .vehicles:
            return "Přehled garáže"
        case .reminders:
            return "Servisní úkoly a termíny"
        case .notifications:
            return "Systémové stavy"
        case .costs:
            return "Vývoj servisních nákladů"
        }
    }

    var iconName: String {
        switch self {
        case .workspace:
            return "rectangle.3.group.fill"
        case .stats:
            return "rectangle.grid.2x2.fill"
        case .quickActions:
            return "bolt.fill"
        case .vehicles:
            return "car.fill"
        case .reminders:
            return "bell.fill"
        case .notifications:
            return "checkmark.bubble.fill"
        case .costs:
            return "chart.bar.fill"
        }
    }
}

private enum DashboardHighlightMode: String, CaseIterable, Identifiable {
    case balanced
    case garage
    case service
    case costs

    var id: String { rawValue }

    var title: String {
        switch self {
        case .balanced:
            return "Vyvážený režim"
        case .garage:
            return "Režim vozidel"
        case .service:
            return "Režim servisu"
        case .costs:
            return "Režim nákladů"
        }
    }

    var subtitle: String {
        switch self {
        case .balanced:
            return "Přehled vozidel, termínů i nákladů v jednom místě"
        case .garage:
            return "Zaměření na garáž, detail vozidel a rychlou správu"
        case .service:
            return "Priorita připomínek, servisních záznamů a nových úkonů"
        case .costs:
            return "Rozpočet, trendy a nákladové souvislosti bez přebytků"
        }
    }

    var iconName: String {
        switch self {
        case .balanced:
            return "square.grid.2x2"
        case .garage:
            return "car.fill"
        case .service:
            return "wrench.and.screwdriver.fill"
        case .costs:
            return "banknote.fill"
        }
    }
}

private struct DashboardWelcomeExperienceView: View {
    @Environment(\.dismiss) private var dismiss
    let onContinue: () -> Void

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: Theme.Spacing.lg) {
                Spacer(minLength: Theme.Spacing.lg)

                VStack(alignment: .leading, spacing: Theme.Spacing.md) {
                    Text("Vítejte na ploše")
                        .font(.system(size: 34, weight: .bold))
                        .foregroundStyle(.white)
                    Text("Dashboard už není jen přehled. Je to pracovní plocha, kterou si nastavíte podle vozidel, servisu, termínů a nákladů.")
                        .font(Theme.Typography.body)
                        .foregroundStyle(Theme.Colors.textSecondary)
                }

                VStack(spacing: Theme.Spacing.sm) {
                    welcomeFeature(
                        title: "Přizpůsobitelné moduly",
                        subtitle: "Skryjte, přesuňte a zvýrazněte jen to, co opravdu používáte.",
                        icon: "slider.horizontal.3"
                    )
                    welcomeFeature(
                        title: "Rychlé pracovní vstupy",
                        subtitle: "Přechod do vozidel, servisu i rezervací bez hledání v aplikaci.",
                        icon: "bolt.fill"
                    )
                    welcomeFeature(
                        title: "Méně šumu, více kontroly",
                        subtitle: "Souhrn, grafy i termíny na jednom místě s jasnou prioritou.",
                        icon: "sparkles"
                    )
                }

                VStack(spacing: Theme.Spacing.sm) {
                    Button {
                        onContinue()
                        dismiss()
                    } label: {
                        Text("Otevřít dashboard")
                            .font(Theme.Typography.bodyStrong)
                            .foregroundStyle(Theme.Colors.background)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, Theme.Spacing.md)
                            .background(Theme.Colors.primary, in: RoundedRectangle(cornerRadius: Theme.Radius.lg, style: .continuous))
                    }
                    .buttonStyle(.plain)

                    Text("Rozložení později upravíte ikonou nastavení vpravo nahoře.")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colors.textSecondary)
                        .frame(maxWidth: .infinity, alignment: .center)
                }

                Spacer()
            }
            .padding(.horizontal, Theme.Spacing.lg)
            .padding(.vertical, Theme.Spacing.lg)
            .hubPageBackground()
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Přeskočit") {
                        onContinue()
                        dismiss()
                    }
                    .foregroundStyle(.white)
                }
            }
        }
    }

    private func welcomeFeature(title: String, subtitle: String, icon: String) -> some View {
        HStack(alignment: .top, spacing: Theme.Spacing.sm) {
            Image(systemName: icon)
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(Theme.Colors.primary)
                .frame(width: 38, height: 38)
                .background(Theme.Colors.primary.opacity(0.16), in: RoundedRectangle(cornerRadius: 12, style: .continuous))

            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(Theme.Typography.bodyStrong)
                    .foregroundStyle(.white)
                Text(subtitle)
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Colors.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Spacer(minLength: 0)
        }
        .padding(Theme.Spacing.md)
        .background(
            RoundedRectangle(cornerRadius: Theme.Radius.lg, style: .continuous)
                .fill(Theme.Colors.surface.opacity(0.92))
        )
        .overlay(
            RoundedRectangle(cornerRadius: Theme.Radius.lg, style: .continuous)
                .stroke(Theme.Colors.hairline, lineWidth: 1)
        )
    }
}

private struct DashboardCustomizationSheet: View {
    @Binding var showWelcomeDeck: Bool
    @Binding var compactMode: Bool
    @Binding var highlightModeRaw: String
    @Binding var moduleOrderRaw: String
    let visibleModules: [DashboardModule: Binding<Bool>]
    @Environment(\.dismiss) private var dismiss
    @State private var orderedModules = DashboardModule.defaultOrder

    private var highlightMode: DashboardHighlightMode {
        DashboardHighlightMode(rawValue: highlightModeRaw) ?? .balanced
    }

    var body: some View {
        NavigationStack {
            List {
                Section("Režim plochy") {
                    Picker("Zaměření", selection: $highlightModeRaw) {
                        ForEach(DashboardHighlightMode.allCases) { mode in
                            Label(mode.title, systemImage: mode.iconName)
                                .tag(mode.rawValue)
                        }
                    }
                    Toggle("Kompaktní hustota rozhraní", isOn: $compactMode)
                }

                Section("Viditelné moduly") {
                    Toggle("Uvítací cockpit", isOn: $showWelcomeDeck)
                    ForEach(orderedModules) { module in
                        if let binding = visibleModules[module] {
                            Toggle(module.title, isOn: binding)
                                .disabled(module == .stats)
                        }
                    }
                }

                Section("Pořadí modulů") {
                    ForEach(Array(orderedModules.enumerated()), id: \.element.id) { index, module in
                        HStack(spacing: Theme.Spacing.sm) {
                            Label {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(module.title)
                                    Text(module.subtitle)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            } icon: {
                                Image(systemName: module.iconName)
                            }

                            Spacer()

                            HStack(spacing: 6) {
                                Button {
                                    moveModule(from: index, offset: -1)
                                } label: {
                                    Image(systemName: "arrow.up")
                                }
                                .disabled(index == 0)

                                Button {
                                    moveModule(from: index, offset: 1)
                                } label: {
                                    Image(systemName: "arrow.down")
                                }
                                .disabled(index == orderedModules.count - 1)
                            }
                            .buttonStyle(.borderless)
                        }
                        .padding(.vertical, 2)
                    }
                }

                Section("Doporučení") {
                    Text(highlightMode.subtitle)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                    Text("První verze přizpůsobení je lokální. Uživatel si tímto upraví vlastní dashboard bez zásahu do dat nebo ostatních sekcí.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Přizpůsobit dashboard")
            .navigationBarTitleDisplayMode(.inline)
            .onAppear {
                orderedModules = DashboardModule.modules(
                    from: moduleOrderRaw,
                    visible: Set(DashboardModule.defaultOrder)
                )
            }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Hotovo") {
                        moduleOrderRaw = orderedModules.map(\.rawValue).joined(separator: ",")
                        dismiss()
                    }
                }
            }
        }
    }

    private func moveModule(from index: Int, offset: Int) {
        let destination = index + offset
        guard orderedModules.indices.contains(index), orderedModules.indices.contains(destination) else { return }
        let item = orderedModules.remove(at: index)
        orderedModules.insert(item, at: destination)
    }
}

private extension Array {
    func chunked(into size: Int) -> [[Element]] {
        guard size > 0 else { return [self] }
        return stride(from: 0, to: count, by: size).map { start in
            Array(self[start..<Swift.min(start + size, count)])
        }
    }
}

private struct CostRecordItem: Identifiable, Hashable {
    let vehicle: Vehicle
    let record: ServiceRecord

    var id: String {
        "\(vehicle.id)-\(record.id)"
    }

    var price: Double? { record.price }
    var date: Date? { record.performedAt }
    var categoryName: String {
        let value = record.category?.trimmingCharacters(in: .whitespacesAndNewlines)
        return (value?.isEmpty == false) ? value! : "Nezařazeno"
    }
}

private struct CostMonthBucket: Identifiable, Hashable {
    let monthStart: Date
    let totalCost: Double
    let recordsCount: Int

    var id: Date { monthStart }

    var label: String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "cs_CZ")
        formatter.dateFormat = "LLL yyyy"
        return formatter.string(from: monthStart)
    }
}

private struct CostVehicleBucket: Identifiable, Hashable {
    let vehicleId: Int
    let title: String
    let totalCost: Double
    let recordsCount: Int

    var id: Int { vehicleId }
}

private struct CostCategoryBucket: Identifiable, Hashable {
    let category: String
    let totalCost: Double
    let recordsCount: Int

    var id: String { category }
}

@MainActor
private final class CostInsightsViewModel: ObservableObject {
    enum PeriodFilter: String, CaseIterable, Identifiable {
        case oneMonth
        case threeMonths
        case sixMonths
        case twelveMonths
        case all

        var id: String { rawValue }

        var title: String {
            switch self {
            case .oneMonth:
                return "1 měsíc"
            case .threeMonths:
                return "3 měsíce"
            case .sixMonths:
                return "6 měsíců"
            case .twelveMonths:
                return "12 měsíců"
            case .all:
                return "Vše"
            }
        }

        var monthsValue: Int? {
            switch self {
            case .oneMonth:
                return 1
            case .threeMonths:
                return 3
            case .sixMonths:
                return 6
            case .twelveMonths:
                return 12
            case .all:
                return nil
            }
        }
    }

    enum PriceFilter: String, CaseIterable, Identifiable {
        case pricedOnly
        case all
        case withoutPriceOnly

        var id: String { rawValue }

        var title: String {
            switch self {
            case .pricedOnly:
                return "Jen s cenou"
            case .all:
                return "Všechny"
            case .withoutPriceOnly:
                return "Bez ceny"
            }
        }
    }

    enum SourceFilter: String, CaseIterable, Identifiable {
        case all
        case manual
        case ai

        var id: String { rawValue }

        var title: String {
            switch self {
            case .all:
                return "Vše"
            case .manual:
                return "Ruční"
            case .ai:
                return "AI"
            }
        }
    }

    @Published var isLoading = false
    @Published var error: String?
    @Published var vehicles: [Vehicle] = []
    @Published var records: [CostRecordItem] = []

    @Published var selectedPeriod: PeriodFilter = .sixMonths
    @Published var selectedVehicleId: Int?
    @Published var selectedCategory: String = "Vše"
    @Published var selectedPriceFilter: PriceFilter = .pricedOnly
    @Published var selectedSourceFilter: SourceFilter = .all
    @Published var searchQuery = ""

    private let vehicleService: VehicleService

    init(vehicleService: VehicleService) {
        self.vehicleService = vehicleService
    }

    func load(token: String) async {
        isLoading = true
        error = nil
        defer { isLoading = false }

        do {
            let loadedVehicles = try await vehicleService.fetchVehicles(token: token)
            var loadedRecords: [CostRecordItem] = []

            for vehicle in loadedVehicles {
                let serviceRecords = try await vehicleService.fetchServiceRecords(vehicleId: vehicle.id, token: token)
                loadedRecords.append(contentsOf: serviceRecords.map { CostRecordItem(vehicle: vehicle, record: $0) })
            }

            vehicles = loadedVehicles.sorted { lhs, rhs in
                lhs.displayName.localizedCaseInsensitiveCompare(rhs.displayName) == .orderedAscending
            }
            records = loadedRecords.sorted { lhs, rhs in
                switch (lhs.date, rhs.date) {
                case let (l?, r?):
                    return l > r
                case (_?, nil):
                    return true
                case (nil, _?):
                    return false
                case (nil, nil):
                    return lhs.id > rhs.id
                }
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    var availableCategories: [String] {
        let categories = Set(records.map(\.categoryName))
        return ["Vše"] + categories.sorted { $0.localizedCaseInsensitiveCompare($1) == .orderedAscending }
    }

    var filteredRecords: [CostRecordItem] {
        var output = records

        if let selectedVehicleId {
            output = output.filter { $0.vehicle.id == selectedVehicleId }
        }

        if let periodStart = periodStartDate {
            output = output.filter { item in
                guard let date = item.date else { return false }
                return date >= periodStart
            }
        }

        if selectedCategory != "Vše" {
            output = output.filter { $0.categoryName == selectedCategory }
        }

        switch selectedPriceFilter {
        case .pricedOnly:
            output = output.filter { $0.price != nil }
        case .withoutPriceOnly:
            output = output.filter { $0.price == nil }
        case .all:
            break
        }

        switch selectedSourceFilter {
        case .all:
            break
        case .manual:
            output = output.filter { !$0.record.createdByAI }
        case .ai:
            output = output.filter { $0.record.createdByAI }
        }

        let query = searchQuery.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if !query.isEmpty {
            output = output.filter { item in
                let searchable = [
                    item.vehicle.displayName,
                    item.vehicle.plate ?? "",
                    item.vehicle.vin ?? "",
                    item.record.description,
                    item.record.note ?? "",
                    item.categoryName
                ]
                .joined(separator: " ")
                .lowercased()
                return searchable.contains(query)
            }
        }

        return output
    }

    var totalCost: Double {
        filteredRecords.compactMap(\.price).reduce(0, +)
    }

    var recordsCount: Int {
        filteredRecords.count
    }

    var pricedRecordsCount: Int {
        filteredRecords.filter { $0.price != nil }.count
    }

    var averageCost: Double? {
        guard pricedRecordsCount > 0 else { return nil }
        return totalCost / Double(pricedRecordsCount)
    }

    var highestCostRecord: CostRecordItem? {
        filteredRecords
            .filter { $0.price != nil }
            .max { lhs, rhs in (lhs.price ?? 0) < (rhs.price ?? 0) }
    }

    var monthlyBuckets: [CostMonthBucket] {
        var grouped: [Date: (sum: Double, count: Int)] = [:]
        let calendar = Calendar.current

        for item in filteredRecords {
            guard let date = item.date, let price = item.price else { continue }
            let monthStart = calendar.date(from: calendar.dateComponents([.year, .month], from: date)) ?? date
            let previous = grouped[monthStart] ?? (0, 0)
            grouped[monthStart] = (previous.sum + price, previous.count + 1)
        }

        return grouped
            .map { CostMonthBucket(monthStart: $0.key, totalCost: $0.value.sum, recordsCount: $0.value.count) }
            .sorted { $0.monthStart < $1.monthStart }
    }

    var vehicleBuckets: [CostVehicleBucket] {
        var grouped: [Int: (title: String, sum: Double, count: Int)] = [:]

        for item in filteredRecords {
            guard let price = item.price else { continue }
            let key = item.vehicle.id
            let previous = grouped[key] ?? (item.vehicle.displayName, 0, 0)
            grouped[key] = (previous.title, previous.sum + price, previous.count + 1)
        }

        return grouped
            .map { CostVehicleBucket(vehicleId: $0.key, title: $0.value.title, totalCost: $0.value.sum, recordsCount: $0.value.count) }
            .sorted { $0.totalCost > $1.totalCost }
    }

    var categoryBuckets: [CostCategoryBucket] {
        var grouped: [String: (sum: Double, count: Int)] = [:]

        for item in filteredRecords {
            guard let price = item.price else { continue }
            let previous = grouped[item.categoryName] ?? (0, 0)
            grouped[item.categoryName] = (previous.sum + price, previous.count + 1)
        }

        return grouped
            .map { CostCategoryBucket(category: $0.key, totalCost: $0.value.sum, recordsCount: $0.value.count) }
            .sorted { $0.totalCost > $1.totalCost }
    }

    private var periodStartDate: Date? {
        guard let months = selectedPeriod.monthsValue else { return nil }
        return Calendar.current.date(byAdding: .month, value: -months, to: Date())
    }
}

private struct CostInsightsView: View {
    @EnvironmentObject private var env: AppEnvironment
    @StateObject private var viewModel = CostInsightsViewModel(vehicleService: VehicleService(api: APIClient()))

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Spacing.lg) {
                filtersSection

                if viewModel.isLoading {
                    ProgressView()
                        .tint(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, Theme.Spacing.xl)
                } else if let error = viewModel.error {
                    ErrorStateView(message: error) {
                        Task { await reload() }
                    }
                } else {
                    summarySection
                    monthlyChartSection
                    categorySection
                    vehicleSection
                    recordsSection
                }
            }
            .padding(.horizontal, Theme.Spacing.md)
            .padding(.top, Theme.Spacing.md)
            .padding(.bottom, Theme.Spacing.xxl + 112)
        }
        .hubPageBackground()
        .navigationTitle("Přehled nákladů")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    Task { await reload() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                        .foregroundStyle(.white.opacity(0.92))
                }
            }
        }
        .task { await reload() }
        .refreshable { await reload() }
    }

    private var filtersSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            SectionHeader(title: "Filtry", subtitle: "Vyberte data, která chcete vidět")

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: Theme.Spacing.sm) {
                    periodMenu
                    vehicleMenu
                    categoryMenu
                    priceMenu
                    sourceMenu
                }
            }

            TextField(
                "",
                text: $viewModel.searchQuery,
                prompt: Text("Hledat podle popisu, VIN, SPZ nebo poznámky")
                    .foregroundStyle(Theme.Colors.textSecondary)
            )
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled(true)
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colors.textPrimary)
                .padding(.horizontal, Theme.Spacing.sm)
                .padding(.vertical, Theme.Spacing.sm)
                .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
        }
        .hubDarkCard()
    }

    private var summarySection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            SectionHeader(title: "Souhrn", subtitle: "Přehled vyfiltrovaných nákladů")

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: Theme.Spacing.sm) {
                CostKpiCard(title: "Celkové náklady", value: formatCurrency(viewModel.totalCost), subtitle: "Součet")
                CostKpiCard(title: "Záznamy", value: "\(viewModel.recordsCount)", subtitle: "Počet")
                CostKpiCard(title: "S cenou", value: "\(viewModel.pricedRecordsCount)", subtitle: "Oceněné")
                CostKpiCard(
                    title: "Průměr",
                    value: viewModel.averageCost.map(formatCurrency) ?? "—",
                    subtitle: "Na záznam"
                )
            }

            if let top = viewModel.highestCostRecord, let price = top.price {
                HStack(spacing: Theme.Spacing.xs) {
                    Image(systemName: "arrow.up.right.circle.fill")
                        .foregroundStyle(Theme.Colors.warning)
                    Text("Nejvyšší položka: \(top.vehicle.displayName) • \(formatCurrency(price))")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colors.textSecondary)
                        .lineLimit(1)
                        .minimumScaleFactor(0.85)
                }
                .padding(.horizontal, Theme.Spacing.sm)
                .padding(.vertical, Theme.Spacing.xs)
                .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
            }
        }
        .hubDarkCard()
    }

    private var monthlyChartSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            SectionHeader(title: "Vývoj nákladů v čase", subtitle: "Měsíční trend podle filtrů")

            if viewModel.monthlyBuckets.isEmpty {
                EmptyStateView(
                    icon: "chart.bar.xaxis",
                    title: "Bez dat pro časový trend",
                    subtitle: "Pro vybrané filtry nebyly nalezeny žádné záznamy s cenou."
                )
            } else {
                Chart(viewModel.monthlyBuckets) { bucket in
                    BarMark(
                        x: .value("Měsíc", bucket.label),
                        y: .value("Náklady", bucket.totalCost)
                    )
                    .foregroundStyle(
                        LinearGradient(
                            colors: [Theme.Colors.primary, Theme.Colors.accent],
                            startPoint: .bottom,
                            endPoint: .top
                        )
                    )
                    .cornerRadius(6)
                }
                .chartXAxis {
                    AxisMarks(values: .automatic) { value in
                        AxisValueLabel {
                            if let label = value.as(String.self) {
                                Text(label)
                                    .font(.system(size: 10, weight: .medium))
                                    .foregroundStyle(Theme.Colors.textOnLightSecondary)
                            }
                        }
                    }
                }
                .chartYAxis {
                    AxisMarks(position: .leading) { value in
                        AxisValueLabel {
                            if let amount = value.as(Double.self) {
                                Text("\(Int(amount))")
                                    .font(.system(size: 10, weight: .medium))
                                    .foregroundStyle(Theme.Colors.textOnLightSecondary)
                            }
                        }
                        AxisGridLine(stroke: StrokeStyle(lineWidth: 0.6, dash: [4, 4]))
                            .foregroundStyle(Theme.Colors.cardHairline.opacity(0.65))
                    }
                }
                .padding(Theme.Spacing.sm)
                .background(Theme.Colors.lightCard, in: RoundedRectangle(cornerRadius: Theme.Radius.lg, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: Theme.Radius.lg, style: .continuous)
                        .stroke(Theme.Colors.cardHairline.opacity(0.7), lineWidth: 1)
                )
                .frame(height: 240)
            }
        }
        .hubDarkCard()
    }

    private var categorySection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            SectionHeader(title: "Kategorie", subtitle: "Rozpad nákladů dle typu servisu", tone: .light)

            if viewModel.categoryBuckets.isEmpty {
                EmptyStateView(
                    icon: "square.grid.2x2",
                    title: "Bez kategorií",
                    subtitle: "Pro vybrané filtry nejsou dostupné cenové položky."
                )
            } else {
                VStack(spacing: Theme.Spacing.sm) {
                    ForEach(viewModel.categoryBuckets) { bucket in
                        HStack(alignment: .center) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(bucket.category)
                                    .font(Theme.Typography.bodyStrong)
                                    .foregroundStyle(Theme.Colors.textOnLight)
                                Text("\(bucket.recordsCount) záznamů")
                                    .font(Theme.Typography.caption)
                                    .foregroundStyle(Theme.Colors.textOnLightSecondary)
                            }
                            Spacer()
                            Text(formatCurrency(bucket.totalCost))
                                .font(Theme.Typography.captionStrong)
                                .foregroundStyle(Theme.Colors.textOnLight)
                        }
                        .padding(.horizontal, Theme.Spacing.sm)
                        .padding(.vertical, Theme.Spacing.xs)
                        .background(Theme.Colors.lightMuted, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
                    }
                }
            }
        }
        .hubLightCard()
    }

    private var vehicleSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            SectionHeader(title: "Vozidla", subtitle: "Náklady podle konkrétního vozidla", tone: .light)

            if viewModel.vehicleBuckets.isEmpty {
                EmptyStateView(
                    icon: "car.fill",
                    title: "Bez nákladů vozidel",
                    subtitle: "Pro vybrané filtry nejsou dostupné cenové položky."
                )
            } else {
                VStack(spacing: Theme.Spacing.sm) {
                    ForEach(viewModel.vehicleBuckets.prefix(8)) { bucket in
                        HStack(alignment: .center) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(bucket.title)
                                    .font(Theme.Typography.bodyStrong)
                                    .foregroundStyle(Theme.Colors.textOnLight)
                                Text("\(bucket.recordsCount) záznamů")
                                    .font(Theme.Typography.caption)
                                    .foregroundStyle(Theme.Colors.textOnLightSecondary)
                            }
                            Spacer()
                            Text(formatCurrency(bucket.totalCost))
                                .font(Theme.Typography.captionStrong)
                                .foregroundStyle(Theme.Colors.textOnLight)
                        }
                        .padding(.horizontal, Theme.Spacing.sm)
                        .padding(.vertical, Theme.Spacing.xs)
                        .background(Theme.Colors.lightMuted, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
                    }
                }
            }
        }
        .hubLightCard()
    }

    private var recordsSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            SectionHeader(title: "Záznamy", subtitle: "Detailní seznam servisních položek", tone: .light)

            if viewModel.filteredRecords.isEmpty {
                EmptyStateView(
                    icon: "doc.text.magnifyingglass",
                    title: "Žádné záznamy",
                    subtitle: "Upravte filtry nebo přidejte nové servisní položky."
                )
            } else {
                VStack(spacing: Theme.Spacing.sm) {
                    ForEach(viewModel.filteredRecords.prefix(120)) { item in
                        NavigationLink {
                            VehicleDetailView(vehicleId: item.vehicle.id)
                        } label: {
                            VStack(alignment: .leading, spacing: 6) {
                                HStack(alignment: .firstTextBaseline) {
                                    Text(item.record.description)
                                        .font(Theme.Typography.bodyStrong)
                                        .foregroundStyle(Theme.Colors.textOnLight)
                                        .lineLimit(2)
                                    Spacer()
                                    Text(item.price.map(formatCurrency) ?? "Cena neuvedena")
                                        .font(Theme.Typography.captionStrong)
                                        .foregroundStyle(Theme.Colors.textOnLight)
                                }

                                Text(item.vehicle.displayName)
                                    .font(Theme.Typography.caption)
                                    .foregroundStyle(Theme.Colors.textOnLightSecondary)

                                HStack(spacing: Theme.Spacing.sm) {
                                    PillBadge(title: item.categoryName)
                                    if let date = item.date {
                                        PillBadge(title: formatDate(date))
                                    }
                                    if let mileage = item.record.mileage {
                                        PillBadge(title: "\(formatNumber(Double(mileage))) km")
                                    }
                                    if item.record.createdByAI {
                                        PillBadge(title: "AI", style: .warning)
                                    }
                                }
                            }
                            .padding(.horizontal, Theme.Spacing.sm)
                            .padding(.vertical, Theme.Spacing.sm)
                            .background(Theme.Colors.lightMuted, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
        .hubLightCard()
    }

    private var periodMenu: some View {
        Menu {
            ForEach(CostInsightsViewModel.PeriodFilter.allCases) { value in
                Button(value.title) {
                    viewModel.selectedPeriod = value
                }
            }
        } label: {
            filterCapsule(title: "Období", value: viewModel.selectedPeriod.title, minWidth: 118)
        }
    }

    private var vehicleMenu: some View {
        Menu {
            Button("Všechna vozidla") {
                viewModel.selectedVehicleId = nil
            }
            Divider()
            ForEach(viewModel.vehicles) { vehicle in
                Button(vehicle.displayName) {
                    viewModel.selectedVehicleId = vehicle.id
                }
            }
        } label: {
            let vehicleTitle = viewModel.vehicles.first(where: { $0.id == viewModel.selectedVehicleId })?.displayName ?? "Všechna"
            filterCapsule(title: "Vozidlo", value: vehicleTitle, minWidth: 198)
        }
    }

    private var categoryMenu: some View {
        Menu {
            ForEach(viewModel.availableCategories, id: \.self) { category in
                Button(category) {
                    viewModel.selectedCategory = category
                }
            }
        } label: {
            filterCapsule(title: "Kategorie", value: viewModel.selectedCategory, minWidth: 154)
        }
    }

    private var priceMenu: some View {
        Menu {
            ForEach(CostInsightsViewModel.PriceFilter.allCases) { value in
                Button(value.title) {
                    viewModel.selectedPriceFilter = value
                }
            }
        } label: {
            filterCapsule(title: "Cena", value: viewModel.selectedPriceFilter.title, minWidth: 136)
        }
    }

    private var sourceMenu: some View {
        Menu {
            ForEach(CostInsightsViewModel.SourceFilter.allCases) { value in
                Button(value.title) {
                    viewModel.selectedSourceFilter = value
                }
            }
        } label: {
            filterCapsule(title: "Zdroj", value: viewModel.selectedSourceFilter.title, minWidth: 118)
        }
    }

    private func filterCapsule(title: String, value: String, minWidth: CGFloat) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(Theme.Typography.tiny)
                .foregroundStyle(Theme.Colors.textSecondary)
            HStack(spacing: 6) {
                Text(value)
                    .font(Theme.Typography.captionStrong)
                    .foregroundStyle(.white)
                    .lineLimit(1)
                Image(systemName: "chevron.down")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(Theme.Colors.textSecondary)
            }
        }
        .padding(.horizontal, Theme.Spacing.sm)
        .padding(.vertical, Theme.Spacing.xs)
        .frame(minWidth: minWidth, alignment: .leading)
        .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
    }

    private func formatCurrency(_ value: Double) -> String {
        let formatter = NumberFormatter()
        formatter.locale = Locale(identifier: "cs_CZ")
        formatter.numberStyle = .currency
        formatter.currencyCode = "CZK"
        formatter.maximumFractionDigits = 0
        return formatter.string(from: NSNumber(value: value)) ?? "\(Int(value)) Kč"
    }

    private func formatDate(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "cs_CZ")
        formatter.dateFormat = "d. M. yyyy"
        return formatter.string(from: date)
    }

    private func formatNumber(_ value: Double) -> String {
        let formatter = NumberFormatter()
        formatter.locale = Locale(identifier: "cs_CZ")
        formatter.numberStyle = .decimal
        formatter.maximumFractionDigits = 0
        formatter.groupingSeparator = " "
        return formatter.string(from: NSNumber(value: value)) ?? "\(Int(value))"
    }

    private func reload() async {
        guard let token = env.authManager.token else { return }
        await viewModel.load(token: token)
    }
}

private struct CostKpiCard: View {
    let title: String
    let value: String
    let subtitle: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(Theme.Typography.tiny)
                .foregroundStyle(Theme.Colors.textSecondary)
            Text(value)
                .font(Theme.Typography.cardTitle)
                .foregroundStyle(.white)
                .monospacedDigit()
                .lineLimit(1)
                .minimumScaleFactor(0.75)
            Text(subtitle)
                .font(Theme.Typography.tiny)
                .foregroundStyle(Theme.Colors.textSecondary)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, minHeight: 92, alignment: .leading)
        .padding(.horizontal, Theme.Spacing.sm)
        .padding(.vertical, Theme.Spacing.xs)
        .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous)
                .stroke(Theme.Colors.hairline.opacity(0.75), lineWidth: 1)
        )
    }
}
