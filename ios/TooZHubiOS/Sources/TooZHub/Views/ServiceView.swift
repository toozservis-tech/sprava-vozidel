import SwiftUI

struct ServiceView: View {
    enum Mode: String, CaseIterable, Identifiable {
        case reminders = "Připomínky"
        case services = "Servisy"

        var id: String { rawValue }

        var icon: String {
            switch self {
            case .reminders:
                return "bell.badge"
            case .services:
                return "wrench.and.screwdriver"
            }
        }
    }

    @EnvironmentObject private var env: AppEnvironment
    @EnvironmentObject private var viewModel: ServiceViewModel
    @State private var mode: Mode = .reminders
    @State private var vehicles: [Vehicle] = []
    @State private var showAddReminder = false
    @State private var addReminderInitialDate: Date?
    @State private var reminderMonth = Date()
    @State private var selectedReminderDate: Date?
    @State private var selectedServiceDetail: ServiceContact?
    @State private var selectedAccessRequest: ServiceAccessRequest?
    @State private var selectedGrantDetail: VehicleAccessGrant?
    @State private var pendingDisconnectService: ServiceContact?
    @State private var pendingGrantRevocation: VehicleAccessGrant?

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: Theme.Spacing.lg) {
                    HStack(alignment: .center) {
                        Text("Připomínky, přístupy a servisní kontakty")
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colors.textSecondary)
                        Spacer()
                        PillBadge(title: mode.rawValue, style: .success)
                    }

                    modeSwitch

                    if viewModel.isLoading {
                        ProgressView()
                            .tint(.white)
                            .frame(maxWidth: .infinity)
                            .padding(.top, 40)
                    } else if mode == .reminders, viewModel.remindersBackendUnavailable {
                        backendUnavailableCard(
                            title: "Připomínky čekají na nasazení",
                            subtitle: "Tento server zatím nevystavuje uživatelské routy pro připomínky. Aplikace proto neukazuje technickou chybu, ale pravdivý release stav."
                        )
                    } else if mode == .services, viewModel.servicesBackendUnavailable {
                        backendUnavailableCard(
                            title: "Servisní kontakty čekají na nasazení",
                            subtitle: "Discovery, přístupy a žádosti nejsou na tomto serveru kompletně dostupné. Po backend deployi se zde zobrazí plný obsah."
                        )
                    } else if let error = viewModel.error {
                        ErrorStateView(message: error) { Task { await reload() } }
                    } else {
                        if mode == .reminders {
                            remindersContent
                        } else {
                            servicesContent
                        }
                    }
                }
                .padding(Theme.Spacing.md)
                .padding(.bottom, Theme.Spacing.xxl + 20)
            }
            .hubPageBackground()
            .navigationTitle("Servisy")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbarBackground(.hidden, for: .navigationBar)
            .toolbar {
                if mode == .reminders {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button {
                            showAddReminder = true
                        } label: {
                            Image(systemName: "plus")
                                .font(.headline.bold())
                                .foregroundStyle(Theme.Colors.textOnLight)
                                .frame(width: 34, height: 34)
                                .background(Theme.Colors.primary, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                        }
                    }
                }
            }
            .sheet(isPresented: $showAddReminder, onDismiss: {
                addReminderInitialDate = nil
            }) {
                AddReminderSheet(vehicles: vehicles, initialDueDate: addReminderInitialDate) { request in
                    guard let token = env.authManager.token else { return }
                    Task { await viewModel.createReminder(request, token: token) }
                }
            }
            .navigationDestination(item: $selectedServiceDetail) { service in
                ServiceDetailView(service: service)
            }
            .navigationDestination(item: $selectedGrantDetail) { grant in
                VehicleServiceLinksView(
                    grant: grant,
                    vehicleName: vehicleName(for: grant.vehicleId),
                    onRevoke: { pendingGrantRevocation = grant }
                )
            }
            .sheet(item: $selectedAccessRequest) { request in
                ServiceAccessRequestSheet(
                    request: request,
                    vehicleName: request.vehicleName ?? vehicleName(for: request.vehicleId),
                    onApprove: {
                        guard let token = env.authManager.token else { return }
                        Task { await viewModel.approveAccessRequest(requestId: request.id, token: token) }
                    },
                    onReject: {
                        guard let token = env.authManager.token else { return }
                        Task { await viewModel.rejectAccessRequest(requestId: request.id, token: token) }
                    }
                )
            }
            .alert(item: $pendingDisconnectService) { service in
                Alert(
                    title: Text("Odpojit servis"),
                    message: Text("Opravdu chcete odpojit servis \(service.name)? Stávající přístupy bude potřeba případně udělit znovu."),
                    primaryButton: .destructive(Text("Odpojit")) {
                        guard let token = env.authManager.token else { return }
                        Task { await viewModel.disconnectService(serviceId: service.id, token: token) }
                    },
                    secondaryButton: .cancel(Text("Zrušit"))
                )
            }
            .alert(item: $pendingGrantRevocation) { grant in
                Alert(
                    title: Text("Odebrat přístup"),
                    message: Text("Odeberete přístup servisu \(grant.serviceName) k vozidlu \(vehicleName(for: grant.vehicleId))."),
                    primaryButton: .destructive(Text("Odebrat")) {
                        guard let token = env.authManager.token else { return }
                        Task {
                            await viewModel.revokeVehicleAccess(
                                serviceId: grant.serviceId,
                                vehicleId: grant.vehicleId,
                                token: token
                            )
                        }
                    },
                    secondaryButton: .cancel(Text("Zrušit"))
                )
            }
            .task(id: mode) { await reload() }
            .refreshable { await reload(force: true) }
        }
    }

    private var modeSwitch: some View {
        HStack(spacing: Theme.Spacing.sm) {
            ForEach(Mode.allCases) { option in
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        mode = option
                    }
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: option.icon)
                        Text(option.rawValue)
                    }
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(InlineChipButtonStyle(isSelected: mode == option))
            }
        }
    }

    private var remindersContent: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            reminderSettingsCard

            ReminderCalendarView(
                reminders: viewModel.reminders,
                selectedMonth: $reminderMonth,
                selectedDate: $selectedReminderDate
            ) { day in
                addReminderInitialDate = day
                showAddReminder = true
            }

            if viewModel.reminders.isEmpty {
                EmptyStateView(
                    icon: "bell.slash",
                    title: "Bez připomínek",
                    subtitle: "Nemáte žádné aktivní připomínky.",
                    actionTitle: "Přidat připomínku"
                ) {
                    showAddReminder = true
                }
            } else {
                VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                    Text(selectedReminderDate == nil ? "Přehled připomínek" : "Připomínky pro vybraný den")
                        .font(Theme.Typography.headline)
                        .foregroundStyle(.white)

                    Text(selectedReminderDate.map { $0.formatted(date: .complete, time: .omitted) } ?? "Klepněte na den v kalendáři nebo pracujte s celkovým přehledem.")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colors.textSecondary)
                }

                ForEach(displayedReminders, id: \.self) { reminder in
                    VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                        TimelineRow(
                            title: reminder.text,
                            subtitle: reminder.vehicleName ?? "Obecná položka",
                            date: reminder.dueDate,
                            color: reminder.isCompleted == true ? .green : Theme.Colors.warning
                        )
                        .padding(.bottom, 2)

                        HStack(spacing: Theme.Spacing.sm) {
                            if canToggleCompletion(reminder) {
                                Button(reminder.isCompleted == true ? "Označit aktivní" : "Dokončit") {
                                    guard let token = env.authManager.token, let id = reminder.id else { return }
                                    Task {
                                        await viewModel.updateReminder(
                                            id: id,
                                            ReminderUpdateRequest(
                                                type: nil,
                                                vehicleId: reminder.vehicleId,
                                                text: reminder.text,
                                                dueDate: reminder.dueDate.map { date in
                                                    let formatter = DateFormatter()
                                                    formatter.locale = Locale(identifier: "en_US_POSIX")
                                                    formatter.timeZone = TimeZone(secondsFromGMT: 0)
                                                    formatter.dateFormat = "yyyy-MM-dd"
                                                    return formatter.string(from: date)
                                                },
                                                notifyAt: reminder.notifyAt,
                                                notificationMethod: reminder.notificationMethod,
                                                isCompleted: !(reminder.isCompleted ?? false)
                                            ),
                                            token: token
                                        )
                                    }
                                }
                                .buttonStyle(InlineChipButtonStyle(isSelected: reminder.isCompleted == true))
                            }

                            if let id = reminder.id {
                                Button("Smazat") {
                                    guard let token = env.authManager.token else { return }
                                    Task { await viewModel.deleteReminder(id: id, token: token) }
                                }
                                .buttonStyle(InlineChipButtonStyle(isSelected: false))
                            }
                        }
                    }
                    .background(
                        RoundedRectangle(cornerRadius: Theme.Radius.lg, style: .continuous)
                            .fill(reminder.isCompleted == true ? Color.green.opacity(0.12) : Theme.Colors.surface)
                    )
                    .hubDarkCard()
                }
            }
        }
    }

    private var reminderSettingsCard: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            Text("Nastavení připomínek")
                .font(Theme.Typography.headline)
                .foregroundStyle(.white)

            Text("Kanál: \(viewModel.reminderSettings?.notification.notificationMethod ?? "app")")
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colors.textSecondary)

            HStack(spacing: Theme.Spacing.sm) {
                Button("App") { updateNotification(method: "app") }
                    .buttonStyle(InlineChipButtonStyle(isSelected: viewModel.reminderSettings?.notification.notificationMethod == "app"))
                Button("Email") { updateNotification(method: "email") }
                    .buttonStyle(InlineChipButtonStyle(isSelected: viewModel.reminderSettings?.notification.notificationMethod == "email"))
                Button("Both") { updateNotification(method: "both") }
                    .buttonStyle(InlineChipButtonStyle(isSelected: viewModel.reminderSettings?.notification.notificationMethod == "both"))
            }

            Text("Předstih: \(viewModel.reminderSettings?.notification.notifyDaysBefore ?? 7) dní")
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colors.textSecondary)
        }
        .hubDarkCard()
    }

    private var servicesContent: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.lg) {
            ServiceDirectoryView(
                services: viewModel.servicesDiscovery,
                onSelectService: { selectedServiceDetail = $0 }
            )

            ServiceAccessRequestsView(
                requests: viewModel.accessRequests,
                vehicleName: vehicleName(for:),
                onOpenRequest: { selectedAccessRequest = $0 },
                onApprove: { request in
                    guard let token = env.authManager.token else { return }
                    Task { await viewModel.approveAccessRequest(requestId: request.id, token: token) }
                },
                onReject: { request in
                    guard let token = env.authManager.token else { return }
                    Task { await viewModel.rejectAccessRequest(requestId: request.id, token: token) }
                }
            )

            serviceBlock(
                title: "Aktivní přístupy k vozidlům",
                subtitle: "Servisy po schválení vidí historii vozidla jen ke čtení a mohou přidat nový servisní záznam."
            ) {
                if viewModel.accessGrants.isEmpty {
                    serviceEmptyCard(
                        title: "Žádné aktivní přístupy",
                        subtitle: "Jakmile schválíte žádost servisu, zobrazí se oprávnění zde."
                    )
                } else {
                    ForEach(viewModel.accessGrants) { grant in
                        accessGrantCard(grant)
                    }
                }
            }

            serviceBlock(
                title: "Propojené servisy",
                subtitle: "Kontakty, se kterými už komunikujete. Samotné propojení ještě neznamená přístup ke všem vozidlům."
            ) {
                if viewModel.myContacts.isEmpty {
                    serviceEmptyCard(
                        title: "Zatím nemáte žádné servisní kontakty",
                        subtitle: "Po prvním spojení nebo komunikaci se servis zobrazí zde."
                    )
                } else {
                    ForEach(viewModel.myContacts) { service in
                        myServiceContactCard(service)
                    }
                }
            }
        }
    }

    private func backendUnavailableCard(title: String, subtitle: String) -> some View {
        EmptyStateView(
            icon: "icloud.slash",
            title: title,
            subtitle: subtitle
        ) {
            Task { await reload(force: true) }
        }
    }

    private func updateNotification(method: String) {
        guard let token = env.authManager.token else { return }
        Task {
            await viewModel.updateReminderSettings(
                notificationMethod: method,
                daysBefore: viewModel.reminderSettings?.notification.notifyDaysBefore ?? 7,
                token: token
            )
        }
    }

    private func reload(force: Bool = false) async {
        guard let token = env.authManager.token else { return }
        switch mode {
        case .reminders:
            await viewModel.loadRemindersIfNeeded(token: token, force: force)
        case .services:
            await viewModel.loadServicesIfNeeded(token: token, force: force)
            if force || vehicles.isEmpty {
                do {
                    vehicles = try await env.vehicleService.fetchVehicles(token: token)
                } catch {
                    viewModel.error = "Nepodařilo se načíst vozidla pro servisní přístupy."
                }
            }
        }
    }

    private var displayedReminders: [Reminder] {
        let source = selectedReminderDate.map { day in
            viewModel.reminders.filter { reminder in
                guard let dueDate = reminder.dueDate else { return false }
                return Calendar.current.isDate(dueDate, inSameDayAs: day)
            }
        } ?? viewModel.reminders

        return source.sorted {
            ($0.dueDate ?? .distantFuture) < ($1.dueDate ?? .distantFuture)
        }
    }

    private func canToggleCompletion(_ reminder: Reminder) -> Bool {
        reminder.id != nil && reminder.isManual
    }

    private func serviceBlock<Content: View>(title: String, subtitle: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            SectionHeader(title: title, subtitle: subtitle)
            content()
        }
    }

    private func availableServiceCard(_ service: ServiceContact) -> some View {
        return VStack(alignment: .leading, spacing: Theme.Spacing.md) {
            Button {
                selectedServiceDetail = service
            } label: {
                HStack(alignment: .top, spacing: Theme.Spacing.sm) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(service.name)
                            .font(Theme.Typography.headline)
                            .foregroundStyle(Theme.Colors.textOnLight)
                            .multilineTextAlignment(.leading)
                        Text(service.discoverySubtitle)
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colors.textOnLightSecondary)
                            .multilineTextAlignment(.leading)
                    }

                    Spacer(minLength: Theme.Spacing.sm)

                    Image(systemName: "chevron.right")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(Theme.Colors.textOnLightSecondary)
                        .padding(.top, 4)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            if let distance = service.distanceKm {
                detailMetaLine(label: "Vzdálenost", value: String(format: "%.1f km", distance))
            }

            Text("Přístup k historii vznikne až tehdy, když servis nejprve najde vozidlo podle SPZ/VIN a vy jeho žádost výslovně schválíte.")
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colors.textOnLightSecondary)

            HStack(spacing: Theme.Spacing.sm) {
                Button("Detail servisu") {
                    selectedServiceDetail = service
                }
                .buttonStyle(InlineChipButtonStyle(isSelected: false))

                if service.phone?.trimmedNonEmpty != nil || service.email.trimmedNonEmpty != nil {
                    Text("Kontakt v detailu")
                        .font(Theme.Typography.captionStrong)
                        .foregroundStyle(Theme.Colors.textOnLight)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, Theme.Spacing.sm)
                        .background(
                            RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous)
                                .fill(Theme.Colors.lightMuted)
                        )
                }
            }
        }
        .hubLightCard()
    }

    private func myServiceContactCard(_ service: ServiceContact) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.md) {
            Button {
                selectedServiceDetail = service
            } label: {
                HStack(alignment: .top, spacing: Theme.Spacing.sm) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(service.name)
                            .font(Theme.Typography.bodyStrong)
                            .foregroundStyle(Theme.Colors.textOnLight)
                        Text(service.discoverySubtitle)
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colors.textOnLightSecondary)
                            .multilineTextAlignment(.leading)
                    }
                    Spacer(minLength: 0)
                    Image(systemName: "chevron.right")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(Theme.Colors.textOnLightSecondary)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            HStack(spacing: Theme.Spacing.sm) {
                detailMetaLine(label: "Email", value: service.email)
                detailMetaLine(label: "Sdílená vozidla", value: "\(service.sharedVehiclesCount)")
            }

            Button(role: .destructive) {
                pendingDisconnectService = service
            } label: {
                Text("Odpojit servis")
                    .font(Theme.Typography.captionStrong)
                    .foregroundStyle(Theme.Colors.danger)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, Theme.Spacing.sm)
                    .background(
                        RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous)
                            .fill(Theme.Colors.danger.opacity(0.10))
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous)
                            .stroke(Theme.Colors.danger.opacity(0.28), lineWidth: 1)
                    )
            }
            .buttonStyle(.plain)
        }
        .hubLightCard()
    }

    private func accessGrantCard(_ grant: VehicleAccessGrant) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.md) {
            HStack(alignment: .top, spacing: Theme.Spacing.sm) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(grant.serviceName)
                        .font(Theme.Typography.bodyStrong)
                        .foregroundStyle(Theme.Colors.textOnLight)
                    Text(grant.serviceEmail)
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colors.textOnLightSecondary)
                }
                Spacer(minLength: 0)
                PillBadge(title: "Aktivní", style: .success)
            }

            HStack(spacing: Theme.Spacing.sm) {
                detailMetaLine(label: "Vozidlo", value: grant.vehicleName ?? vehicleName(for: grant.vehicleId))
                detailMetaLine(label: "Uděleno", value: formattedGrantDate(grant.updatedAt))
            }

            HStack(spacing: Theme.Spacing.sm) {
                Button("Zobrazit detail") {
                    selectedGrantDetail = grant
                }
                .buttonStyle(InlineChipButtonStyle(isSelected: false))

                Button(role: .destructive) {
                    pendingGrantRevocation = grant
                } label: {
                    Text("Odebrat přístup")
                }
                .buttonStyle(InlineChipButtonStyle(isSelected: false))
            }
        }
        .hubLightCard()
    }

    private func serviceEmptyCard(title: String, subtitle: String) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
            Text(title)
                .font(Theme.Typography.bodyStrong)
                .foregroundStyle(Theme.Colors.textOnLight)
            Text(subtitle)
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colors.textOnLightSecondary)
        }
        .hubLightCard()
    }

    private func detailMetaLine(label: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(Theme.Typography.tiny)
                .foregroundStyle(Theme.Colors.textOnLightSecondary)
            Text(value)
                .font(Theme.Typography.captionStrong)
                .foregroundStyle(Theme.Colors.textOnLight)
                .lineLimit(2)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(Theme.Spacing.sm)
        .background(Theme.Colors.lightMuted, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
    }

    private func vehicleName(for vehicleId: Int) -> String {
        vehicles.first(where: { $0.id == vehicleId })?.displayName ?? "Vozidlo #\(vehicleId)"
    }

    private func vehicleIdentityText(_ vehicle: Vehicle?) -> String {
        guard let vehicle else { return "Neurčené vozidlo" }
        if let plate = vehicle.plate, !plate.isEmpty {
            return plate
        }
        if let vin = vehicle.vin, !vin.isEmpty {
            return vin
        }
        return "Bez SPZ a VIN"
    }

    private func formattedGrantDate(_ value: String?) -> String {
        guard let value, !value.isEmpty else { return "Neznámé datum" }
        let formatter = ISO8601DateFormatter()
        if let date = formatter.date(from: value) {
            return date.formatted(date: .abbreviated, time: .omitted)
        }
        return value
    }
}

struct AddReminderSheet: View {
    let vehicles: [Vehicle]
    let initialDueDate: Date?
    let onSubmit: (ReminderCreateRequest) -> Void
    @Environment(\.dismiss) private var dismiss

    @State private var title = ""
    @State private var note = ""
    @State private var type = ReminderTypeOption.defaultOption
    @State private var dueDate = Date().addingTimeInterval(7 * 24 * 3600)
    @State private var vehicleId: Int? = nil
    @State private var validationMessage: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Spacing.lg) {
                    sheetSection(
                        title: "Základ",
                        subtitle: "Vyplňte, co se má připomenout a kdy."
                    ) {
                        VStack(spacing: Theme.Spacing.sm) {
                            VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                                fieldLabel("Název připomínky", required: true)
                                TextField("Např. Objednat STK", text: $title)
                                    .accountTextFieldStyle()
                                Text("Krátký a srozumitelný název, který uvidíte v přehledu.")
                                    .font(Theme.Typography.tiny)
                                    .foregroundStyle(Theme.Colors.textSecondary)
                            }

                            VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                                fieldLabel("Typ", required: true)
                                LazyVGrid(columns: [GridItem(.adaptive(minimum: 110), spacing: Theme.Spacing.xs)], spacing: Theme.Spacing.xs) {
                                    ForEach(ReminderTypeOption.supportedCases) { option in
                                        Button {
                                            type = option
                                        } label: {
                                            Text(option.label)
                                                .frame(maxWidth: .infinity)
                                        }
                                        .buttonStyle(InlineChipButtonStyle(isSelected: type == option))
                                    }
                                }
                            }

                            VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                                fieldLabel("Datum", required: true)
                                DatePicker("Termín", selection: $dueDate, in: startOfToday..., displayedComponents: .date)
                                    .datePickerStyle(.graphical)
                                    .labelsHidden()
                                    .padding(Theme.Spacing.sm)
                                    .background(Theme.Colors.inputSurface, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
                            }
                        }
                    }

                    sheetSection(
                        title: "Vazba na vozidlo",
                        subtitle: "Pokud nevyberete žádné vozidlo, uloží se jako obecná připomínka."
                    ) {
                        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                            Menu {
                                Button("Obecná připomínka") {
                                    vehicleId = nil
                                }
                                ForEach(vehicles) { vehicle in
                                    Button(vehicle.displayName) {
                                        vehicleId = vehicle.id
                                    }
                                }
                            } label: {
                                HStack(spacing: Theme.Spacing.sm) {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(selectedVehicleTitle)
                                            .font(Theme.Typography.bodyStrong)
                                            .foregroundStyle(.white)
                                        Text(selectedVehicleSubtitle)
                                            .font(Theme.Typography.caption)
                                            .foregroundStyle(Theme.Colors.textSecondary)
                                    }
                                    Spacer(minLength: 0)
                                    Image(systemName: "chevron.down")
                                        .font(.caption.weight(.bold))
                                        .foregroundStyle(Theme.Colors.textSecondary)
                                }
                                .padding(Theme.Spacing.sm)
                                .background(Theme.Colors.inputSurface, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
                            }
                            .buttonStyle(.plain)
                        }
                    }

                    sheetSection(
                        title: "Detail",
                        subtitle: "Poznámka je volitelná. Backend ji zatím neumí uložit odděleně, proto se připojí k textu připomínky."
                    ) {
                        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                            fieldLabel("Poznámka", required: false)
                            TextField("Volitelně doplňte detail", text: $note, axis: .vertical)
                                .lineLimit(2...5)
                                .accountTextFieldStyle()
                        }
                    }

                    if let validationMessage, !validationMessage.isEmpty {
                        Text(validationMessage)
                            .font(Theme.Typography.captionStrong)
                            .foregroundStyle(Theme.Colors.warning)
                    }
                }
                .padding(Theme.Spacing.md)
                .padding(.bottom, Theme.Spacing.xl)
            }
            .background(Theme.Colors.background.ignoresSafeArea())
            .navigationTitle("Nová připomínka")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Zrušit") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Uložit") {
                        submit()
                    }
                    .disabled(!canSubmit)
                }
            }
            .onAppear {
                if let initialDueDate {
                    dueDate = initialDueDate
                }
            }
            .onChange(of: title) { _, _ in
                validationMessage = nil
            }
            .onChange(of: note) { _, _ in
                validationMessage = nil
            }
        }
    }

    private var startOfToday: Date {
        Calendar.current.startOfDay(for: Date())
    }

    private var trimmedTitle: String {
        title.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var trimmedNote: String {
        note.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var canSubmit: Bool {
        trimmedTitle.count >= 3
    }

    private var selectedVehicleTitle: String {
        vehicles.first(where: { $0.id == vehicleId })?.displayName ?? "Obecná připomínka"
    }

    private var selectedVehicleSubtitle: String {
        if let vehicle = vehicles.first(where: { $0.id == vehicleId }) {
            return vehicle.plate?.isEmpty == false ? vehicle.plate! : (vehicle.vin ?? "Konkrétní vozidlo")
        }
        return "Bez vazby na konkrétní vozidlo"
    }

    private func submit() {
        guard canSubmit else {
            validationMessage = "Vyplňte název připomínky alespoň o 3 znacích."
            return
        }

        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd"

        let fullText = trimmedNote.isEmpty ? trimmedTitle : "\(trimmedTitle)\n\(trimmedNote)"
        onSubmit(
            ReminderCreateRequest(
                vehicleId: vehicleId,
                type: type.apiValue,
                text: fullText,
                dueDate: formatter.string(from: dueDate),
                notifyAt: nil,
                notificationMethod: nil,
                repeatCount: 0,
                repeatIntervalDays: 0
            )
        )
        dismiss()
    }

    private func sheetSection<Content: View>(title: String, subtitle: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            Text(title)
                .font(Theme.Typography.headline)
                .foregroundStyle(.white)
            Text(subtitle)
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colors.textSecondary)
            content()
        }
        .hubDarkCard()
    }

    private func fieldLabel(_ title: String, required: Bool) -> some View {
        HStack(spacing: 4) {
            Text(title)
                .font(Theme.Typography.captionStrong)
                .foregroundStyle(.white)
            if required {
                Text("Povinné")
                    .font(Theme.Typography.tiny)
                    .foregroundStyle(Theme.Colors.warning)
            }
        }
    }
}

private struct ReminderTypeOption: Identifiable, Equatable {
    let id: String
    let label: String
    let apiValue: String

    static let custom = ReminderTypeOption(id: "custom", label: "Vlastní", apiValue: "VLASTNI")
    static let stk = ReminderTypeOption(id: "stk", label: "STK", apiValue: "STK")
    static let service = ReminderTypeOption(id: "service", label: "Servis", apiValue: "SERVIS")
    static let insurance = ReminderTypeOption(id: "insurance", label: "Pojistka", apiValue: "POJISTKA")
    static let emissions = ReminderTypeOption(id: "emissions", label: "Emise", apiValue: "EMISE")

    static let defaultOption = custom
    static let supportedCases: [ReminderTypeOption] = [.custom, .stk, .service, .insurance, .emissions]
}

private struct ServiceTextFieldModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
            .font(Theme.Typography.body)
            .foregroundColor(.white)
            .tint(.white)
            .padding(.horizontal, Theme.Spacing.sm)
            .padding(.vertical, 12)
            .background(
                RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous)
                    .fill(Theme.Colors.inputSurface)
            )
            .overlay(
                RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous)
                    .stroke(Theme.Colors.textSecondary.opacity(0.18), lineWidth: 1)
            )
            .environment(\.colorScheme, .dark)
    }
}

private extension View {
    func accountTextFieldStyle() -> some View {
        modifier(ServiceTextFieldModifier())
    }
}

private struct ServiceDirectoryView: View {
    let services: [ServiceContact]
    let onSelectService: (ServiceContact) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            SectionHeader(
                title: "Přehled servisů v ČR",
                subtitle: "Seznam je řazený od nejbližšího. Samotné zobrazení servisu ještě neznamená přístup k vašemu vozidlu."
            )

            if services.isEmpty {
                VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                    Text("Katalog servisů je zatím prázdný")
                        .font(Theme.Typography.bodyStrong)
                        .foregroundStyle(Theme.Colors.textOnLight)
                    Text("Jakmile backend vrátí registrované servisy, uvidíte je zde včetně vzdálenosti.")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colors.textOnLightSecondary)
                }
                .hubLightCard()
            } else {
                ForEach(services) { service in
                    Button {
                        onSelectService(service)
                    } label: {
                        HStack(alignment: .top, spacing: Theme.Spacing.sm) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(service.name)
                                    .font(Theme.Typography.bodyStrong)
                                    .foregroundStyle(Theme.Colors.textOnLight)
                                    .multilineTextAlignment(.leading)
                                Text(service.discoverySubtitle)
                                    .font(Theme.Typography.caption)
                                    .foregroundStyle(Theme.Colors.textOnLightSecondary)
                                Text(service.distanceLabel)
                                    .font(Theme.Typography.captionStrong)
                                    .foregroundStyle(Theme.Colors.primaryDark)
                            }

                            Spacer(minLength: 0)

                            Image(systemName: "chevron.right")
                                .font(.caption.weight(.bold))
                                .foregroundStyle(Theme.Colors.textOnLightSecondary)
                                .padding(.top, 4)
                        }
                        .padding(.vertical, Theme.Spacing.xs)
                    }
                    .buttonStyle(.plain)
                    .hubLightCard()
                }
            }
        }
    }
}

private struct ServiceAccessRequestsView: View {
    let requests: [ServiceAccessRequest]
    let vehicleName: (Int) -> String
    let onOpenRequest: (ServiceAccessRequest) -> Void
    let onApprove: (ServiceAccessRequest) -> Void
    let onReject: (ServiceAccessRequest) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            SectionHeader(
                title: "Čekající žádosti o přístup",
                subtitle: "Schvalujete jen čtení historie vozidla a možnost přidat nový servisní záznam. Staré záznamy servis měnit nesmí."
            )

            if requests.isEmpty {
                VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                    Text("Aktuálně nečeká žádná žádost")
                        .font(Theme.Typography.bodyStrong)
                        .foregroundStyle(Theme.Colors.textOnLight)
                    Text("Až servis požádá o přístup k nalezenému vozidlu, objeví se žádost zde.")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colors.textOnLightSecondary)
                }
                .hubLightCard()
            } else {
                ForEach(requests) { request in
                    VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                        HStack(alignment: .top, spacing: Theme.Spacing.sm) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(request.serviceName)
                                    .font(Theme.Typography.bodyStrong)
                                    .foregroundStyle(Theme.Colors.textOnLight)
                                Text(request.vehicleName ?? vehicleName(request.vehicleId))
                                    .font(Theme.Typography.caption)
                                    .foregroundStyle(Theme.Colors.textOnLightSecondary)
                            }
                            Spacer(minLength: 0)
                            PillBadge(title: "Čeká", style: .warning)
                        }

                        if let note = request.note?.trimmedNonEmpty {
                            Text(note)
                                .font(Theme.Typography.caption)
                                .foregroundStyle(Theme.Colors.textOnLightSecondary)
                        }

                        HStack(spacing: Theme.Spacing.sm) {
                            Button("Detail") {
                                onOpenRequest(request)
                            }
                            .buttonStyle(InlineChipButtonStyle(isSelected: false))

                            Button("Schválit") {
                                onApprove(request)
                            }
                            .buttonStyle(InlineChipButtonStyle(isSelected: true))

                            Button("Zamítnout") {
                                onReject(request)
                            }
                            .buttonStyle(InlineChipButtonStyle(isSelected: false))
                        }
                    }
                    .hubLightCard()
                }
            }
        }
    }
}

private struct VehicleServiceLinksView: View {
    let grant: VehicleAccessGrant
    let vehicleName: String
    let onRevoke: () -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Spacing.lg) {
                VStack(alignment: .leading, spacing: Theme.Spacing.md) {
                    Text(grant.serviceName)
                        .font(Theme.Typography.cardTitle)
                        .foregroundStyle(.white)
                    Text(vehicleName)
                        .font(Theme.Typography.body)
                        .foregroundStyle(Theme.Colors.textSecondary)

                    VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                        permissionRow(title: "Rozsah přístupu", value: "Čtení historie vozidla")
                        permissionRow(title: "Co servis smí", value: "Vytvořit nový servisní záznam")
                        permissionRow(title: "Co servis nesmí", value: "Měnit nebo mazat staré cizí záznamy")
                        permissionRow(title: "Platné od", value: formattedGrantDate(grant.updatedAt))
                    }
                }
                .hubDarkCard()

                Button(role: .destructive) {
                    onRevoke()
                } label: {
                    Text("Odebrat přístup")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(PrimaryActionButtonStyle())
            }
            .padding(Theme.Spacing.md)
            .padding(.bottom, Theme.Spacing.xxl + 20)
        }
        .hubPageBackground()
        .navigationTitle("Přístup servisu")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .toolbarBackground(.hidden, for: .navigationBar)
    }

    private func permissionRow(title: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(Theme.Typography.tiny)
                .foregroundStyle(Theme.Colors.textSecondary)
            Text(value)
                .font(Theme.Typography.bodyStrong)
                .foregroundStyle(.white)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(Color.white.opacity(0.05))
        )
    }

    private func formattedGrantDate(_ value: String?) -> String {
        guard let value, !value.isEmpty else { return "Neznámé datum" }
        let formatter = ISO8601DateFormatter()
        if let date = formatter.date(from: value) {
            return date.formatted(date: .abbreviated, time: .omitted)
        }
        return value
    }
}

private struct ServiceAccessRequestSheet: View {
    let request: ServiceAccessRequest
    let vehicleName: String
    let onApprove: () -> Void
    let onReject: () -> Void

    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Spacing.lg) {
                    VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                        Text(request.serviceName)
                            .font(Theme.Typography.cardTitle)
                            .foregroundStyle(.white)
                        Text(vehicleName)
                            .font(Theme.Typography.body)
                            .foregroundStyle(Theme.Colors.textSecondary)
                        if let requestedAt = request.requestedAt?.trimmedNonEmpty {
                            Text("Žádost vytvořena: \(formattedDate(requestedAt))")
                                .font(Theme.Typography.caption)
                                .foregroundStyle(Theme.Colors.textSecondary)
                        }
                    }
                    .hubDarkCard()

                    VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                        SectionHeader(
                            title: "Co schvalujete",
                            subtitle: "Schválení nedává servisu plný přístup k vozidlu. Povolené je jen to, co je níže."
                        )
                        if let scopeSummary = request.scopeSummary?.trimmedNonEmpty {
                            approvalRuleRow(scopeSummary)
                        }
                        approvalRuleRow("Servis po schválení uvidí historii vozidla jen ke čtení.")
                        approvalRuleRow("Servis může založit nový servisní záznam.")
                        approvalRuleRow("Servis nesmí upravovat ani mazat starší cizí záznamy.")
                    }
                    .hubDarkCard()

                    if let note = request.note?.trimmedNonEmpty {
                        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                            Text("Poznámka od servisu")
                                .font(Theme.Typography.captionStrong)
                                .foregroundStyle(.white)
                            Text(note)
                                .font(Theme.Typography.body)
                                .foregroundStyle(Theme.Colors.textSecondary)
                        }
                        .hubDarkCard()
                    }

                    HStack(spacing: Theme.Spacing.sm) {
                        Button("Zamítnout") {
                            onReject()
                            dismiss()
                        }
                        .buttonStyle(InlineChipButtonStyle(isSelected: false))

                        Button("Schválit") {
                            onApprove()
                            dismiss()
                        }
                        .buttonStyle(PrimaryActionButtonStyle())
                    }
                }
                .padding(Theme.Spacing.md)
                .padding(.bottom, Theme.Spacing.xxl + 20)
            }
            .hubPageBackground()
            .navigationTitle("Žádost o přístup")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Zavřít") { dismiss() }
                }
            }
        }
    }

    private func approvalRuleRow(_ text: String) -> some View {
        HStack(alignment: .top, spacing: Theme.Spacing.sm) {
            Image(systemName: "checkmark.shield")
                .foregroundStyle(Theme.Colors.primary)
            Text(text)
                .font(Theme.Typography.body)
                .foregroundStyle(.white)
        }
    }

    private func formattedDate(_ value: String) -> String {
        let formatter = ISO8601DateFormatter()
        if let date = formatter.date(from: value) {
            return date.formatted(date: .abbreviated, time: .omitted)
        }
        return value
    }
}

private struct ServiceDetailView: View {
    let service: ServiceContact
    @Environment(\.openURL) private var openURL

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Spacing.lg) {
                heroCard

                if quickActionsAvailable {
                    VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                        SectionHeader(title: "Rychlé akce", subtitle: "Kontaktujte servis nebo otevřete lokaci")

                        VStack(spacing: Theme.Spacing.sm) {
                            if let phoneURL {
                                quickActionButton("Zavolat", icon: "phone.fill", tint: Theme.Colors.primary) {
                                    openURL(phoneURL)
                                }
                            }
                            if let mailURL {
                                quickActionButton("Napsat email", icon: "envelope.fill", tint: Theme.Colors.accent) {
                                    openURL(mailURL)
                                }
                            }
                            if let mapsURL {
                                quickActionButton("Otevřít v Mapách", icon: "map.fill", tint: Theme.Colors.primaryDark) {
                                    openURL(mapsURL)
                                }
                            }
                        }
                    }
                }

                VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                    SectionHeader(title: "Přístup k vozidlu", subtitle: "Servis neuvidí historii jen podle SPZ nebo VIN.")
                    detailRow(title: "Jak to funguje", value: "Servis může vozidlo jen dohledat jako kandidáta. Přístup ke čtení historie a možnost přidat nový servisní záznam vzniká až po vašem schválení žádosti.")
                    detailRow(title: "Omezení", value: "Starší cizí záznamy servis nemůže měnit ani mazat.")
                }
                .hubDarkCard()

                VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                    SectionHeader(title: "Kontaktní údaje", subtitle: "Detail servisního partnera")

                    detailRow(title: "Název", value: service.name)
                    detailRow(title: "Email", value: service.email.trimmedNonEmpty ?? "Neuvedeno")
                    detailRow(title: "Telefon", value: service.phone.nonEmptyFallback("Neuvedeno"))
                    detailRow(title: "Město", value: service.city.nonEmptyFallback("Neuvedeno"))
                    detailRow(title: "Adresa", value: service.fullAddress.nonEmptyFallback("Neuvedeno"))
                    detailRow(title: "IČO", value: service.ico.nonEmptyFallback("Neuvedeno"))
                    if let distance = service.distanceKm {
                        detailRow(title: "Vzdálenost", value: String(format: "%.1f km", distance))
                    }
                    detailRow(title: "Sdílená vozidla", value: "\(service.sharedVehiclesCount)")
                    detailRow(title: "Propojeno", value: service.isLinked ? "Ano" : "Ne")
                }
                .hubDarkCard()
            }
            .padding(Theme.Spacing.md)
            .padding(.bottom, Theme.Spacing.xxl + 20)
        }
        .hubPageBackground()
        .navigationTitle("Detail servisu")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .toolbarBackground(.hidden, for: .navigationBar)
    }

    private var heroCard: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.md) {
            HStack(alignment: .top, spacing: Theme.Spacing.sm) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(service.name)
                        .font(Theme.Typography.cardTitle)
                        .foregroundStyle(.white)
                    Text(service.discoverySubtitle)
                        .font(Theme.Typography.body)
                        .foregroundStyle(Theme.Colors.textSecondary)
                }
                Spacer(minLength: Theme.Spacing.sm)
                if service.isLinked {
                    PillBadge(title: "Propojeno", style: .success)
                }
            }

            HStack(spacing: Theme.Spacing.sm) {
                contactStat(title: "Město", value: service.city.nonEmptyFallback("—"), icon: "building.2.fill")
                contactStat(title: "Kontakt", value: service.phone.nonEmptyFallback(service.email.trimmedNonEmpty ?? "—"), icon: "phone.fill")
            }
        }
        .hubDarkCard()
    }

    private var quickActionsAvailable: Bool {
        phoneURL != nil || mailURL != nil || mapsURL != nil
    }

    private var phoneURL: URL? {
        guard let phone = service.phone?.digitsAndPhoneSymbolsOnly, !phone.isEmpty else { return nil }
        return URL(string: "tel://\(phone)")
    }

    private var mailURL: URL? {
        guard let email = service.email.trimmedNonEmpty?.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) else { return nil }
        return URL(string: "mailto:\(email)")
    }

    private var mapsURL: URL? {
        guard let rawAddress = service.fullAddress,
              let address = rawAddress.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed),
              !address.isEmpty else { return nil }
        return URL(string: "http://maps.apple.com/?q=\(address)")
    }

    private func contactStat(title: String, value: String, icon: String) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
            Image(systemName: icon)
                .font(.headline.weight(.semibold))
                .foregroundStyle(Theme.Colors.primary)
            Text(title)
                .font(Theme.Typography.tiny)
                .foregroundStyle(Theme.Colors.textSecondary)
            Text(value)
                .font(Theme.Typography.bodyStrong)
                .foregroundStyle(.white)
                .lineLimit(2)
                .minimumScaleFactor(0.8)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(Color.white.opacity(0.07))
        )
    }

    private func quickActionButton(_ title: String, icon: String, tint: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: Theme.Spacing.sm) {
                Image(systemName: icon)
                    .font(.headline.weight(.semibold))
                Text(title)
                    .font(Theme.Typography.bodyStrong)
                Spacer()
                Image(systemName: "arrow.up.right")
                    .font(.caption.weight(.bold))
            }
            .foregroundStyle(.white)
            .padding()
            .background(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(tint.opacity(0.82))
            )
        }
        .buttonStyle(.plain)
    }

    private func detailRow(title: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title.uppercased())
                .font(Theme.Typography.tiny)
                .foregroundStyle(Theme.Colors.textSecondary)
            Text(value)
                .font(Theme.Typography.body)
                .foregroundStyle(.white)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(Color.white.opacity(0.05))
        )
    }
}

private extension ServiceContact {
    var distanceLabel: String {
        guard let distanceKm else { return "Vzdálenost zatím není k dispozici" }
        return String(format: "Vzdálenost %.1f km", distanceKm)
    }

    var discoverySubtitle: String {
        let location = city?.trimmingCharacters(in: .whitespacesAndNewlines)
        let emailText = email.trimmingCharacters(in: .whitespacesAndNewlines)
        switch (location?.isEmpty == false ? location : nil, emailText.isEmpty ? nil : emailText) {
        case let (.some(city), .some(email)):
            return "\(city) • \(email)"
        case let (.some(city), nil):
            return city
        case let (nil, .some(email)):
            return email
        default:
            return "Kontakt není doplněn"
        }
    }

    var fullAddress: String? {
        let streetParts = [street?.trimmedNonEmpty, streetNumber?.trimmedNonEmpty].compactMap { $0 }
        let cityParts = [zip?.trimmedNonEmpty, city?.trimmedNonEmpty].compactMap { $0 }
        let parts = [
            streetParts.isEmpty ? nil : streetParts.joined(separator: " "),
            cityParts.isEmpty ? nil : cityParts.joined(separator: " ")
        ].compactMap { $0 }
        return parts.isEmpty ? nil : parts.joined(separator: ", ")
    }
}

private extension Optional where Wrapped == String {
    func nonEmptyFallback(_ fallback: String) -> String {
        self?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false ? self!.trimmingCharacters(in: .whitespacesAndNewlines) : fallback
    }
}

private extension String {
    var trimmedNonEmpty: String? {
        let trimmed = trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    var digitsAndPhoneSymbolsOnly: String {
        filter { $0.isNumber || $0 == "+" }
    }
}
