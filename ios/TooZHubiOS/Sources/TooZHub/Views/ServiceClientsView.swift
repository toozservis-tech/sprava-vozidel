import SwiftUI

struct ServiceClientsView: View {
    @EnvironmentObject private var env: AppEnvironment
    @StateObject private var viewModel: ServiceClientsViewModel
    @State private var selectedLookupCandidate: ServiceVehicleLookupCandidate?
    @State private var selectedVehicleContext: ServiceVehicleContext?
    @State private var requestSendError: String?
    @State private var requestSendSuccess: String?

    init() {
        _viewModel = StateObject(wrappedValue: ServiceClientsViewModel(service: ServiceWorkspaceService(api: APIClient())))
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Spacing.lg) {
                    SectionHeader(
                        title: "Vozidla klientů / Připojit vozidlo",
                        subtitle: "Servis může vozidlo najít podle SPZ nebo VIN, ale historii uvidí až po schválení uživatelem.",
                        trailing: AnyView(PillBadge(title: "\(viewModel.approvedVehicles.count)", style: .success))
                    )

                    if viewModel.isLoading {
                        ProgressView()
                            .tint(.white)
                            .frame(maxWidth: .infinity)
                            .padding(.top, 60)
                    } else if let error = viewModel.error {
                        ErrorStateView(message: error) { Task { await reload() } }
                    } else {
                        if viewModel.loadState == .backendUnavailable {
                            InlineFeedbackCard(
                                message: "Nový servisní přístup zatím na tomto serveru není nasazený. Lookup, žádosti i schválená vozidla budou dostupné až po backend deployi.",
                                tone: .warning
                            )
                        }

                        if viewModel.loadState != .legacyWorkspaceReady {
                            ServiceVehicleLookupView(
                                query: $viewModel.lookupQuery,
                                isLoading: viewModel.isLookupLoading,
                                error: viewModel.lookupError,
                                state: viewModel.lookupState,
                                onRegisterNewVehicle: {
                                    env.requestedServiceTab = "addVehicle"
                                },
                                onSubmit: {
                                    guard let token = env.authManager.token else { return }
                                    Task { await viewModel.lookupVehicle(token: token) }
                                }
                            )
                        } else {
                            legacyWorkspaceBanner
                            serviceCustomerSection
                        }

                        if let requestSendSuccess {
                            InlineFeedbackCard(message: requestSendSuccess, tone: .success)
                        }

                        if let requestSendError {
                            InlineFeedbackCard(message: requestSendError, tone: .warning)
                        }

                        if !viewModel.lookupResults.isEmpty {
                            ServiceVehicleLookupResultView(
                                candidates: viewModel.lookupResults,
                                onOpen: { selectedLookupCandidate = $0 }
                            )
                        }

                        if viewModel.loadState == .legacyWorkspaceReady {
                            legacyVehiclesSection
                        } else {
                            approvedVehiclesSection
                        }

                        if viewModel.loadState == .serviceAccessReady && viewModel.approvedVehicles.isEmpty {
                            EmptyStateView(
                                icon: "car.2",
                                title: "Zatím nemáte schválená vozidla",
                                subtitle: "Jakmile uživatel schválí servisní přístup, uvidíte vozidla klientů zde."
                            )
                        }
                    }
                }
                .padding(Theme.Spacing.md)
                .padding(.bottom, Theme.Spacing.xxl + 18)
            }
            .hubPageBackground()
            .navigationTitle("Klienti")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbarBackground(.hidden, for: .navigationBar)
            .navigationDestination(item: $selectedVehicleContext) { vehicle in
                ServiceVehicleDetailView(vehicle: vehicle)
            }
            .sheet(item: $selectedLookupCandidate) { candidate in
                ServiceAccessRequestComposerSheet(candidate: candidate) { note in
                    guard let token = env.authManager.token else { return }
                    Task {
                        do {
                            let message = try await viewModel.sendAccessRequest(candidate: candidate, note: note, token: token)
                            requestSendError = nil
                            requestSendSuccess = message
                            await viewModel.lookupVehicle(token: token)
                        } catch {
                            requestSendSuccess = nil
                            requestSendError = UserFacingErrorMapper.message(
                                for: error,
                                context: .account,
                                fallback: "Žádost o přístup se nepodařilo odeslat. Zkuste to prosím znovu."
                            )
                        }
                    }
                }
            }
            .task { await reload() }
            .refreshable { await reload() }
        }
    }

    private func reload() async {
        guard let token = env.authManager.token else { return }
        await viewModel.load(token: token)
    }

    private var legacyWorkspaceBanner: some View {
        InlineFeedbackCard(
            message: "Server zatím běží v kompatibilním servisním režimu. Klienty a jejich vozidla používáte přes legacy workspace, zatímco nový access model čeká na deploy.",
            tone: .success
        )
    }

    private var serviceCustomerSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            SectionHeader(
                title: "Klienti servisu",
                subtitle: "Kompatibilní servisní workspace pro práci s již propojenými zákazníky a jejich vozidly."
            )

            if viewModel.customers.isEmpty {
                EmptyStateView(
                    icon: "person.3",
                    title: "Zatím nemáte propojené klienty",
                    subtitle: "Jakmile bude klient se servisem propojený, uvidíte ho zde."
                )
            } else {
                ForEach(viewModel.customers) { customer in
                    VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                        Text(customer.name ?? customer.email)
                            .font(Theme.Typography.headline)
                            .foregroundStyle(.white)

                        Text(customer.email)
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colors.textSecondary)

                        Text("Vozidla: \(customer.vehiclesCount) • Sdílená: \(customer.sharedVehiclesCount)")
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colors.textSecondary)

                        HStack {
                            Button("Načíst vozidla klienta") {
                                guard let token = env.authManager.token else { return }
                                Task { await viewModel.selectCustomer(customer.customerId, token: token) }
                            }
                            .buttonStyle(InlineChipButtonStyle(isSelected: viewModel.selectedCustomerId == customer.customerId))

                            Spacer()

                            if viewModel.selectedCustomerId == customer.customerId {
                                PillBadge(title: "Vybráno", style: .success)
                            }
                        }
                    }
                    .hubDarkCard()
                }
            }
        }
    }

    private var approvedVehiclesSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            SectionHeader(
                title: "Schválená vozidla",
                subtitle: "Tento seznam už používá skutečný backend kontrakt pro schválené přístupy."
            )

            if viewModel.loadState == .backendUnavailable {
                EmptyStateView(
                    icon: "wrench.and.screwdriver",
                    title: "Servisní přístup čeká na nasazení",
                    subtitle: "Tento server ještě nevystavuje nové endpointy pro lookup vozidla, žádosti o přístup a schválená vozidla."
                )
            } else {
                ForEach(viewModel.approvedVehicles) { vehicle in
                    Button {
                        selectedVehicleContext = ServiceVehicleContext(approvedVehicle: vehicle)
                    } label: {
                        HStack(alignment: .top, spacing: Theme.Spacing.sm) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(vehicle.displayName)
                                    .font(Theme.Typography.bodyStrong)
                                    .foregroundStyle(.white)
                                Text(vehicle.vehiclePlate ?? "Bez SPZ")
                                    .font(Theme.Typography.caption)
                                    .foregroundStyle(Theme.Colors.textSecondary)
                                if let customerName = vehicle.customerName, !customerName.isEmpty {
                                    Text(customerName)
                                        .font(Theme.Typography.caption)
                                        .foregroundStyle(Theme.Colors.textSecondary)
                                }
                                if let lastSharedAt = vehicle.lastSharedAt, !lastSharedAt.isEmpty {
                                    Text("Schváleno: \(formatBackendDate(lastSharedAt))")
                                        .font(Theme.Typography.caption)
                                        .foregroundStyle(Theme.Colors.textSecondary)
                                }
                                Text("Historie je pouze ke čtení")
                                    .font(Theme.Typography.captionStrong)
                                    .foregroundStyle(Theme.Colors.accent)
                            }
                            Spacer(minLength: 0)
                            Image(systemName: "chevron.right")
                                .foregroundStyle(Theme.Colors.textSecondary)
                        }
                        .padding(.vertical, Theme.Spacing.xs)
                    }
                    .buttonStyle(.plain)
                    .hubDarkCard()
                }
            }
        }
    }

    private var legacyVehiclesSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            SectionHeader(
                title: "Vozidla klienta",
                subtitle: "Legacy servisní workspace. Vozidla můžete otevřít a pracovat se servisní historií podle aktuálních práv serveru."
            )

            if viewModel.selectedCustomerVehicles.isEmpty {
                EmptyStateView(
                    icon: "car.2",
                    title: "Vyberte klienta",
                    subtitle: "Po výběru klienta se zde zobrazí jeho vozidla dostupná servisu."
                )
            } else {
                ForEach(viewModel.selectedCustomerVehicles) { vehicle in
                    Button {
                        let customerName = viewModel.customers.first(where: { $0.customerId == viewModel.selectedCustomerId })?.name
                            ?? viewModel.customers.first(where: { $0.customerId == viewModel.selectedCustomerId })?.email
                        selectedVehicleContext = ServiceVehicleContext(legacyVehicle: vehicle, customerName: customerName)
                    } label: {
                        HStack(alignment: .top, spacing: Theme.Spacing.sm) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(vehicle.displayName)
                                    .font(Theme.Typography.bodyStrong)
                                    .foregroundStyle(.white)
                                Text(vehicle.plate ?? vehicle.vin ?? "Bez SPZ a VIN")
                                    .font(Theme.Typography.caption)
                                    .foregroundStyle(Theme.Colors.textSecondary)
                                if let mileage = vehicle.currentMileageKm {
                                    Text("Aktuální km: \(mileage.formatted()) km")
                                        .font(Theme.Typography.caption)
                                        .foregroundStyle(Theme.Colors.textSecondary)
                                }
                                Text("Otevřít detail vozidla")
                                    .font(Theme.Typography.captionStrong)
                                    .foregroundStyle(Theme.Colors.accent)
                            }
                            Spacer(minLength: 0)
                            Image(systemName: "chevron.right")
                                .foregroundStyle(Theme.Colors.textSecondary)
                        }
                        .padding(.vertical, Theme.Spacing.xs)
                    }
                    .buttonStyle(.plain)
                    .hubDarkCard()
                }
            }
        }
    }
}

private struct ServiceVehicleLookupView: View {
    @Binding var query: String
    let isLoading: Bool
    let error: String?
    let state: ServiceClientsViewModel.LookupState
    let onRegisterNewVehicle: () -> Void
    let onSubmit: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            SectionHeader(
                title: "Připojit vozidlo",
                subtitle: "Zadejte SPZ nebo VIN. Bez schválení uživatelem neuvidíte plnou historii vozidla."
            )

            TextField("Např. 1AB2345 nebo VIN", text: $query)
                .textInputAutocapitalization(.characters)
                .autocorrectionDisabled()
                .serviceLookupTextFieldStyle()

            if let error {
                Text(error)
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Colors.warning)
            } else {
                lookupStateText
            }

            Button(isLoading ? "Vyhledávám..." : "Vyhledat vozidlo") {
                onSubmit()
            }
            .buttonStyle(PrimaryActionButtonStyle())
            .disabled(isLoading || query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
        .hubDarkCard()
    }

    @ViewBuilder
    private var lookupStateText: some View {
        switch state {
        case .idle:
            EmptyView()
        case .found:
            Text("Vozidlo bylo nalezeno. Před schválením uvidíte jen omezená data kandidáta.")
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colors.textSecondary)
        case .pendingRequest:
            Text("Pro toto vozidlo už existuje čekající žádost o přístup.")
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colors.warning)
        case .alreadyApproved:
            Text("K tomuto vozidlu už máte schválený přístup.")
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colors.accent)
        case .notFound:
            VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                Text("Pro zadanou SPZ nebo VIN nebyl nalezen žádný kandidát vozidla.")
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Colors.warning)
                Button("Zařadit nové vozidlo a pozvat majitele") {
                    onRegisterNewVehicle()
                }
                .buttonStyle(InlineChipButtonStyle(isSelected: true))
            }
        }
    }
}

private struct ServiceVehicleLookupResultView: View {
    let candidates: [ServiceVehicleLookupCandidate]
    let onOpen: (ServiceVehicleLookupCandidate) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            SectionHeader(
                title: "Výsledek lookupu",
                subtitle: "Před schválením zobrazujeme jen omezenou identifikaci vozidla."
            )

            ForEach(candidates) { candidate in
                Button {
                    onOpen(candidate)
                } label: {
                    HStack(alignment: .top, spacing: Theme.Spacing.sm) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(candidate.displayName)
                                .font(Theme.Typography.bodyStrong)
                                .foregroundStyle(.white)
                            Text([candidate.plateMasked, candidate.vinMasked].compactMap { $0 }.joined(separator: " • "))
                                .font(Theme.Typography.caption)
                                .foregroundStyle(Theme.Colors.textSecondary)
                            Text(candidate.statusLabel)
                                .font(Theme.Typography.captionStrong)
                                .foregroundStyle(candidate.statusTint)
                        }

                        Spacer(minLength: 0)
                        Image(systemName: "chevron.right")
                            .foregroundStyle(Theme.Colors.textSecondary)
                    }
                    .padding(.vertical, Theme.Spacing.xs)
                }
                .buttonStyle(.plain)
                .disabled(!candidate.canRequestAccess)
                .hubDarkCard()
            }
        }
    }
}

private struct ServiceAccessRequestComposerSheet: View {
    let candidate: ServiceVehicleLookupCandidate
    let onSubmit: (String?) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var note = ""

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Spacing.lg) {
                    VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                        Text(candidate.displayName)
                            .font(Theme.Typography.cardTitle)
                            .foregroundStyle(.white)
                        Text([candidate.plateMasked, candidate.vinMasked].compactMap { $0 }.joined(separator: " • "))
                            .font(Theme.Typography.body)
                            .foregroundStyle(Theme.Colors.textSecondary)
                    }
                    .hubDarkCard()

                    VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                        SectionHeader(
                            title: "Žádost o přístup",
                            subtitle: "Po odeslání žádosti uživatel uvidí, že chcete číst historii vozidla a přidat nový servisní záznam. Bez schválení neuvidíte plnou historii."
                        )

                        TextField("Doplňující poznámka pro uživatele", text: $note, axis: .vertical)
                            .lineLimit(3...6)
                            .serviceLookupTextFieldStyle()
                    }
                    .hubDarkCard()

                    Button("Odeslat žádost o přístup") {
                        onSubmit(note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? nil : note)
                        dismiss()
                    }
                    .buttonStyle(PrimaryActionButtonStyle())
                    .disabled(!candidate.canRequestAccess)
                }
                .padding(Theme.Spacing.md)
                .padding(.bottom, Theme.Spacing.xxl + 20)
            }
            .hubPageBackground()
            .navigationTitle("Žádost servisu")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Zavřít") { dismiss() }
                }
            }
        }
    }
}

private struct ServiceVehicleDetailView: View {
    @EnvironmentObject private var env: AppEnvironment
    let vehicle: ServiceVehicleContext

    @State private var records: [ServiceRecord] = []
    @State private var isLoading = false
    @State private var error: String?
    @State private var showAddRecord = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Spacing.lg) {
                VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                    Text(vehicle.title)
                        .font(Theme.Typography.cardTitle)
                        .foregroundStyle(.white)
                    Text([vehicle.plate, vehicle.vin].compactMap { $0 }.joined(separator: " • ").isEmpty ? "Bez SPZ a VIN" : [vehicle.plate, vehicle.vin].compactMap { $0 }.joined(separator: " • "))
                        .font(Theme.Typography.body)
                        .foregroundStyle(Theme.Colors.textSecondary)
                    if let customerName = vehicle.customerName, !customerName.isEmpty {
                        Text(customerName)
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colors.textSecondary)
                    }
                    if let approvedAtLabel = vehicle.approvedAtLabel, !approvedAtLabel.isEmpty {
                        Text("Přístup aktivní od: \(formatBackendDate(approvedAtLabel))")
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colors.textSecondary)
                    }

                    HStack(spacing: Theme.Spacing.sm) {
                        serviceDetailMetricCard(
                            title: "Zdroj",
                            value: vehicle.source == .approvedAccess ? "Schválený přístup" : "Legacy workspace"
                        )
                        if let currentMileageKm = vehicle.currentMileageKm {
                            serviceDetailMetricCard(
                                title: "Aktuální km",
                                value: "\(currentMileageKm.formatted()) km"
                            )
                        }
                    }

                    if let stkValidUntil = vehicle.stkValidUntil, !stkValidUntil.isEmpty {
                        serviceDetailMetricCard(title: "STK do", value: formatBackendDate(stkValidUntil))
                    }

                    readOnlyRule("Historii vozidla vidíte pouze ke čtení.")
                    readOnlyRule("Můžete přidat nový servisní záznam.")
                    readOnlyRule("Staré záznamy jiných subjektů nesmíte měnit ani mazat.")
                }
                .hubDarkCard()

                if isLoading {
                    ProgressView()
                        .tint(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.top, 24)
                } else if let error {
                    ErrorStateView(message: error) { Task { await reload() } }
                } else if records.isEmpty {
                    EmptyStateView(
                        icon: "doc.text.magnifyingglass",
                        title: "Zatím bez servisních záznamů",
                        subtitle: "Pro toto schválené vozidlo zatím backend nevrátil žádné servisní záznamy."
                    ) {
                        showAddRecord = true
                    }
                } else {
                    VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                        SectionHeader(title: "Servisní historie", subtitle: "Read-only přehled záznamů")
                        ForEach(records) { record in
                            VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                                Text(record.description)
                                    .font(Theme.Typography.bodyStrong)
                                    .foregroundStyle(.white)
                                Text(record.performedAt?.formatted(date: .abbreviated, time: .omitted) ?? "Bez data")
                                    .font(Theme.Typography.caption)
                                    .foregroundStyle(Theme.Colors.textSecondary)
                                if let mileage = record.mileage {
                                    Text("Stav km: \(mileage.formatted()) km")
                                        .font(Theme.Typography.caption)
                                        .foregroundStyle(Theme.Colors.textSecondary)
                                }
                            }
                            .hubDarkCard()
                        }
                    }
                }
            }
            .padding(Theme.Spacing.md)
            .padding(.bottom, Theme.Spacing.xxl + 20)
        }
        .hubPageBackground()
        .navigationTitle("Detail vozidla")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .toolbarBackground(.hidden, for: .navigationBar)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    showAddRecord = true
                } label: {
                    Image(systemName: "plus")
                }
            }
        }
        .sheet(isPresented: $showAddRecord) {
            AddServiceRecordSheet(vehicleId: vehicle.id) { request in
                guard let token = env.authManager.token else { return }
                Task {
                    do {
                        _ = try await env.userFeatureService.createServiceRecord(vehicleId: vehicle.id, request, token: token)
                        await reload()
                    } catch {
                        self.error = UserFacingErrorMapper.message(
                            for: error,
                            context: .account,
                            fallback: "Nový servisní záznam se nepodařilo uložit."
                        )
                    }
                }
            }
        }
        .task { await reload() }
    }

    private func reload() async {
        guard let token = env.authManager.token else { return }
        isLoading = true
        error = nil
        defer { isLoading = false }

        do {
            records = try await env.vehicleService.fetchServiceRecords(vehicleId: vehicle.id, token: token)
        } catch {
            self.error = UserFacingErrorMapper.message(
                for: error,
                context: .vehicleDetailLoad,
                            fallback: "Schválenou historii vozidla se nepodařilo načíst."
            )
        }
    }

    private func readOnlyRule(_ text: String) -> some View {
        HStack(alignment: .top, spacing: Theme.Spacing.sm) {
            Image(systemName: "lock.shield")
                .foregroundStyle(Theme.Colors.primary)
            Text(text)
                .font(Theme.Typography.body)
                .foregroundStyle(.white)
        }
    }

    private func serviceDetailMetricCard(title: String, value: String) -> some View {
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
}

private struct InlineFeedbackCard: View {
    enum Tone {
        case success
        case warning
    }

    let message: String
    let tone: Tone

    var body: some View {
        Text(message)
            .font(Theme.Typography.captionStrong)
            .foregroundStyle(.white)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding()
            .background(backgroundColor, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    private var backgroundColor: Color {
        switch tone {
        case .success:
            return Theme.Colors.accent.opacity(0.8)
        case .warning:
            return Theme.Colors.warning.opacity(0.8)
        }
    }
}

private struct ServiceLookupTextFieldModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding(.horizontal, Theme.Spacing.md)
            .padding(.vertical, Theme.Spacing.sm)
            .background(
                RoundedRectangle(cornerRadius: Theme.Radius.lg, style: .continuous)
                    .fill(Color.white.opacity(0.08))
            )
            .overlay(
                RoundedRectangle(cornerRadius: Theme.Radius.lg, style: .continuous)
                    .stroke(Theme.Colors.hairline, lineWidth: 1)
            )
            .foregroundStyle(.white)
    }
}

private extension View {
    func serviceLookupTextFieldStyle() -> some View {
        modifier(ServiceLookupTextFieldModifier())
    }
}

private func formatBackendDate(_ value: String) -> String {
    let isoFormatter = ISO8601DateFormatter()
    if let date = isoFormatter.date(from: value) {
        return date.formatted(date: .abbreviated, time: .omitted)
    }
    return value
}

private extension ServiceVehicleLookupCandidate {
    var statusLabel: String {
        switch status {
        case "pending_request":
            return "Čekající žádost už existuje"
        case "already_approved":
            return "Přístup už je schválený"
        case "matched":
            return "Lze požádat o přístup"
        default:
            return canRequestAccess ? "Lze požádat o přístup" : "Žádost není dostupná"
        }
    }

    var statusTint: Color {
        switch status {
        case "already_approved":
            return Theme.Colors.accent
        case "pending_request":
            return Theme.Colors.warning
        case "matched":
            return Theme.Colors.accent
        default:
            return canRequestAccess ? Theme.Colors.accent : Theme.Colors.warning
        }
    }
}
