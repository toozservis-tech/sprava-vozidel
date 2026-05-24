import SwiftUI
import UIKit
import VisionKit

struct VehiclesView: View {
    @EnvironmentObject private var env: AppEnvironment
    @EnvironmentObject private var viewModel: VehiclesViewModel

    @AppStorage("vehicle_list_mode") private var vehicleListModeRawValue = VehicleCardMode.grid.rawValue
    @State private var showAddVehicle = false
    @State private var editVehicle: Vehicle?
    @State private var selectedVehicleForDetail: Vehicle?
    @State private var vehiclePendingRemoval: Vehicle?

    private var selectedMode: VehicleCardMode {
        get { VehicleCardMode(rawValue: vehicleListModeRawValue) ?? .grid }
        nonmutating set { vehicleListModeRawValue = newValue.rawValue }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: Theme.Spacing.lg) {
                    HStack(alignment: .center) {
                        Text("Správa garáže a detailů vozidel")
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colors.textSecondary)
                        Spacer()
                        PillBadge(title: "\(viewModel.vehicles.count) vozidel", style: .success)
                    }

                    modeSwitch

                    if viewModel.isLoading {
                        ProgressView()
                            .tint(.white)
                            .frame(maxWidth: .infinity)
                            .padding(.top, 60)
                    } else if let error = viewModel.error {
                        ErrorStateView(message: error) { Task { await reload() } }
                    } else if viewModel.vehicles.isEmpty {
                        EmptyStateView(
                            icon: "car.rear",
                            title: "Zatím nemáte žádné vozidlo",
                            subtitle: "Přidejte první auto a sledujte servisní historii i náklady.",
                            actionTitle: "Přidat vozidlo"
                        ) {
                            showAddVehicle = true
                        }
                    } else {
                        Group {
                            switch selectedMode {
                            case .grid:
                                LazyVGrid(columns: [GridItem(.adaptive(minimum: 260), spacing: Theme.Spacing.md)], spacing: Theme.Spacing.md) {
                                    ForEach(viewModel.vehicles) { vehicle in
                                        vehicleItem(vehicle)
                                    }
                                }
                            case .list, .compact:
                                LazyVStack(spacing: Theme.Spacing.md) {
                                    ForEach(viewModel.vehicles) { vehicle in
                                        vehicleItem(vehicle)
                                    }
                                }
                            }
                        }
                    }
                }
                .padding(Theme.Spacing.md)
                .padding(.bottom, Theme.Spacing.xxl + 24)
            }
            .hubPageBackground()
            .navigationTitle("Vozidla")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbarBackground(.hidden, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showAddVehicle = true
                    } label: {
                        Image(systemName: "plus")
                            .font(.headline.bold())
                            .foregroundStyle(Theme.Colors.textOnLight)
                            .frame(width: 34, height: 34)
                            .background(Theme.Colors.primary, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    }
                }
            }
            .sheet(isPresented: $showAddVehicle) {
                AddOrEditVehicleSheet(vehicle: nil, existingVehicles: viewModel.vehicles) { request in
                    guard let token = env.authManager.token else { return }
                    try await viewModel.createVehicle(request, token: token)
                }
            }
            .sheet(item: $selectedVehicleForDetail) { vehicle in
                NavigationStack {
                    VehicleDetailView(vehicleId: vehicle.id)
                }
            }
            .sheet(item: $vehiclePendingRemoval) { vehicle in
                VehicleRemovalSheet(vehicleId: vehicle.id, vehicleLabel: vehicle.displayName) { vid, reasonCode, followup in
                    guard let token = env.authManager.token else {
                        throw APIError.serverError("Nejste přihlášeni.")
                    }
                    return try await viewModel.removeVehicleFromAccount(
                        id: vid,
                        reasonCode: reasonCode,
                        followup: followup,
                        token: token
                    )
                }
            }
            .sheet(item: $editVehicle) { vehicle in
                AddOrEditVehicleSheet(vehicle: vehicle, existingVehicles: viewModel.vehicles) { request in
                    guard let token = env.authManager.token else { return }
                    try await viewModel.updateVehicle(id: vehicle.id, request: request, token: token)
                }
            }
            .refreshable { await reload(force: true) }
            .task { await reload() }
        }
    }

    private func reload(force: Bool = false) async {
        guard let token = env.authManager.token else { return }
        await viewModel.loadIfNeeded(token: token, force: force)
    }

    private var modeSwitch: some View {
        HStack(spacing: Theme.Spacing.sm) {
            ForEach(VehicleCardMode.allCases) { mode in
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        selectedMode = mode
                    }
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: mode.icon)
                        Text(mode.title)
                    }
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(InlineChipButtonStyle(isSelected: selectedMode == mode))
            }
        }
    }

    private func vehicleItem(_ vehicle: Vehicle) -> some View {
        VStack(spacing: Theme.Spacing.sm) {
            Button {
                selectedVehicleForDetail = vehicle
            } label: {
                VehicleCard(vehicle: vehicle, mode: selectedMode)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .buttonStyle(.plain)

            HStack(spacing: Theme.Spacing.sm) {
                Button("Upravit") {
                    editVehicle = vehicle
                }
                .buttonStyle(InlineChipButtonStyle(isSelected: true))

                Button("Odebrat z profilu") {
                    vehiclePendingRemoval = vehicle
                }
                .buttonStyle(InlineChipButtonStyle(isSelected: false))
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

private struct TachometerCaptchaSheet: View {
    let challenge: TachometerChallengeResponse
    let isSubmitting: Bool
    let errorMessage: String?
    let onSubmit: (String) -> Void
    let onCancel: () -> Void

    @State private var captchaCode = ""

    private var captchaImage: UIImage? {
        guard let data = Data(base64Encoded: challenge.captchaImageBase64) else { return nil }
        return UIImage(data: data)
    }

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: Theme.Spacing.md) {
                Text("Opište kód z obrázku pro ověření na Kontrole tachometru.")
                    .font(Theme.Typography.body)
                    .foregroundStyle(Theme.Colors.textSecondary)

                if let captchaImage {
                    Image(uiImage: captchaImage)
                        .resizable()
                        .interpolation(.none)
                        .scaledToFit()
                        .frame(maxWidth: .infinity)
                        .frame(height: 92)
                        .padding(Theme.Spacing.sm)
                        .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))
                } else {
                    Text("Captcha obrázek se nepodařilo načíst.")
                        .font(Theme.Typography.body)
                        .foregroundStyle(.red)
                }

                TextField("Kód z obrázku", text: $captchaCode)
                    .textInputAutocapitalization(.characters)
                    .autocorrectionDisabled(true)
                    .font(Theme.Typography.body)
                    .padding(.horizontal, Theme.Spacing.md)
                    .padding(.vertical, Theme.Spacing.sm)
                    .background(Theme.Colors.elevated, in: RoundedRectangle(cornerRadius: Theme.Radius.md, style: .continuous))

                if let errorMessage, !errorMessage.isEmpty {
                    Text(errorMessage)
                        .font(Theme.Typography.caption)
                        .foregroundStyle(.red)
                }

                if isSubmitting {
                    HStack(spacing: Theme.Spacing.sm) {
                        ProgressView()
                        Text("Ověřuji…")
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colors.textSecondary)
                    }
                }

                Spacer(minLength: 0)
            }
            .padding(Theme.Spacing.md)
            .navigationTitle("Ověření captchy")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Zavřít") { onCancel() }
                        .disabled(isSubmitting)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Načíst km") {
                        onSubmit(captchaCode)
                    }
                    .disabled(
                        isSubmitting ||
                        captchaCode.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    )
                }
            }
        }
        .presentationDetents([.medium])
    }
}

struct AddOrEditVehicleSheet: View {
    let vehicle: Vehicle?
    let existingVehicles: [Vehicle]
    let onSubmit: (VehicleCreateRequest) async throws -> Void

    @EnvironmentObject private var env: AppEnvironment
    @Environment(\.dismiss) private var dismiss
    @State private var nickname = ""
    @State private var brand = ""
    @State private var model = ""
    @State private var year = ""
    @State private var engine = ""
    @State private var vin = ""
    @State private var plate = ""
    @State private var notes = ""
    @State private var currentMileageKm = ""
    @State private var lastStkMileageKm = ""
    @State private var stkDate = Date().addingTimeInterval(365 * 24 * 3600)
    @State private var vinLookupMessage: String?
    @State private var vinLookupError: String?
    @State private var isLookingUpVIN = false
    @State private var isLookingUpTachometer = false
    @State private var tachometerChallenge: TachometerChallengeResponse?
    @State private var showTachometerCaptchaSheet = false
    @State private var hasManualNicknameOverride = false
    @State private var isSyncingNickname = false
    @State private var isSubmitting = false
    @State private var submitError: String?
    @State private var showORVScanFlow = false
    @State private var appliedORVScan: ORVScanReviewResult?

    private let vehicleService = VehicleService(api: APIClient())
    private var parsedCurrentMileageKm: Int? { parseMileageInput(currentMileageKm) }
    private var parsedLastStkMileageKm: Int? { parseMileageInput(lastStkMileageKm) }
    private var normalizedCurrentVIN: String { VehicleInputValidator.normalizedVIN(vin) }
    private var duplicateVINError: String? {
        guard !normalizedCurrentVIN.isEmpty else { return nil }

        let colliding = existingVehicles.first { candidate in
            guard candidate.id != vehicle?.id else { return false }
            let normalizedCandidateVIN = VehicleInputValidator.normalizedVIN(candidate.vin ?? "")
            return !normalizedCandidateVIN.isEmpty && normalizedCandidateVIN == normalizedCurrentVIN
        }
        guard colliding != nil else { return nil }
        return "Vozidlo s tímto VIN už existuje."
    }

    private var mileageValidationError: String? {
        guard
            let current = parsedCurrentMileageKm,
            let lastStk = parsedLastStkMileageKm,
            current < lastStk
        else { return nil }
        return "Aktuální stav km musí být alespoň \(formatMileage(lastStk)) km (poslední údaj ze STK/emisí)."
    }

    private var orvValidationError: String? {
        guard appliedORVScan != nil else { return nil }
        return VehicleInputValidator.validationMessage(for: vin, required: true)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Přidání pomocí ORV") {
                    Button {
                        showORVScanFlow = true
                    } label: {
                        Label("Naskenovat ORV", systemImage: "doc.text.viewfinder")
                    }

                    if let appliedORVScan {
                        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                            Text("Údaje z ORV jsou připravené ve formuláři")
                                .font(Theme.Typography.body)
                                .foregroundStyle(Theme.Colors.textPrimary)
                            Text("Po kontrole v aplikaci: \(appliedORVScan.reviewTrustStateLabel)")
                                .font(Theme.Typography.caption)
                                .foregroundStyle(Theme.Colors.textSecondary)
                            Text("Při finálním uložení vozidla se scan uloží jako: \(appliedORVScan.persistedTrustStateLabel)")
                                .font(Theme.Typography.caption)
                                .foregroundStyle(Theme.Colors.textSecondary)
                            Text("Vozidlo se vytvoří nebo upraví až po stisku tlačítka Uložit.")
                                .font(Theme.Typography.caption)
                                .foregroundStyle(Theme.Colors.textSecondary)
                            if !appliedORVScan.vehicleFields.orvNumber.isEmpty {
                                let orvNumber = appliedORVScan.vehicleFields.orvNumber
                                Text("Číslo ORV: \(orvNumber)")
                                    .font(Theme.Typography.caption)
                                    .foregroundStyle(Theme.Colors.textSecondary)
                            }
                            if appliedORVScan.includeOwnerData {
                                Text("Volba použití osobních údajů z ORV je připravená pro finální uložení.")
                                    .font(Theme.Typography.caption)
                                    .foregroundStyle(Theme.Colors.textSecondary)
                            }
                            ForEach(appliedORVScan.warnings, id: \.self) { warning in
                                Text(warning)
                                    .font(Theme.Typography.caption)
                                    .foregroundStyle(.orange)
                            }
                        }
                    }
                }
                Section("Základní údaje") {
                    HStack {
                        TextField("VIN", text: $vin)
                            .textInputAutocapitalization(.characters)
                            .autocorrectionDisabled(true)
                        Button("Načíst z VIN") {
                            Task { await decodeVIN() }
                        }
                        .disabled(isLookingUpVIN || !VehicleInputValidator.isValidVIN(vin))
                    }
                    TextField("Název", text: $nickname)
                    TextField("Značka", text: $brand)
                    TextField("Model", text: $model)
                    TextField("Rok výroby", text: $year)
                        .keyboardType(.numberPad)
                    TextField("Motor", text: $engine)
                    HStack {
                        TextField("SPZ", text: $plate)
                            .textInputAutocapitalization(.characters)
                            .autocorrectionDisabled(true)
                        Button("Načíst ze SPZ") {
                            Task { await decodePlate() }
                        }
                        .disabled(isLookingUpVIN || plate.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }
                    DatePicker("STK", selection: $stkDate, displayedComponents: .date)
                    TextField("Aktuální stav km", text: $currentMileageKm)
                        .keyboardType(.numberPad)
                    TextField("Poslední km ze STK/emisí", text: $lastStkMileageKm)
                        .keyboardType(.numberPad)
                    Button {
                        Task { await startTachometerLookup() }
                    } label: {
                        HStack {
                            if isLookingUpTachometer {
                                ProgressView()
                            }
                            Text("Načíst poslední km z Kontroly tachometru")
                        }
                    }
                    .disabled(
                        isLookingUpVIN ||
                        isLookingUpTachometer ||
                        !VehicleInputValidator.isValidVIN(vin)
                    )
                    TextField("Poznámky", text: $notes, axis: .vertical)
                        .lineLimit(2...4)
                }
                if let mileageValidationError {
                    Section {
                        Text(mileageValidationError)
                            .foregroundStyle(.red)
                    }
                }
                if let duplicateVINError {
                    Section {
                        Text(duplicateVINError)
                            .foregroundStyle(.red)
                    }
                }
                if let orvValidationError {
                    Section {
                        Text(orvValidationError)
                            .foregroundStyle(.red)
                    }
                }
                if let message = vinLookupMessage {
                    Section {
                        Text(message)
                            .foregroundStyle(Theme.Colors.accent)
                    }
                }
                if let error = vinLookupError {
                    Section {
                        Text(error)
                            .foregroundStyle(.red)
                    }
                }
                if let submitError {
                    Section {
                        Text(submitError)
                            .foregroundStyle(.red)
                    }
                }
            }
            .navigationTitle(vehicle == nil ? "Přidat vozidlo" : "Upravit vozidlo")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Zrušit") { dismiss() }
                        .disabled(isSubmitting)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Uložit") {
                        Task { await submitVehicle() }
                    }
                    .disabled(
                        isSubmitting ||
                        nickname.trimmingCharacters(in: .whitespacesAndNewlines).count < 2 ||
                        mileageValidationError != nil ||
                        duplicateVINError != nil ||
                        orvValidationError != nil
                    )
                }
            }
            .sheet(isPresented: $showTachometerCaptchaSheet) {
                if let challenge = tachometerChallenge {
                    TachometerCaptchaSheet(
                        challenge: challenge,
                        isSubmitting: isLookingUpTachometer,
                        errorMessage: vinLookupError,
                        onSubmit: { code in
                            Task { await submitTachometerLookup(captchaCode: code) }
                        },
                        onCancel: {
                            showTachometerCaptchaSheet = false
                            tachometerChallenge = nil
                        }
                    )
                }
            }
            .sheet(isPresented: $showORVScanFlow) {
                ORVScanFlowSheet { result in
                    applyORVScanResult(result)
                    showORVScanFlow = false
                }
            }
            .onAppear {
                nickname = vehicle?.nickname ?? ""
                brand = vehicle?.brand ?? ""
                model = vehicle?.model ?? ""
                year = vehicle?.year.map(String.init) ?? ""
                engine = vehicle?.engine ?? ""
                vin = vehicle?.vin ?? ""
                plate = vehicle?.plate ?? ""
                notes = vehicle?.notes ?? ""
                currentMileageKm = vehicle?.currentMileageKm.map(String.init) ?? ""
                lastStkMileageKm = vehicle?.lastStkMileageKm.map(String.init) ?? ""
                stkDate = vehicle?.stkValidUntil ?? Date().addingTimeInterval(365 * 24 * 3600)
                hasManualNicknameOverride = vehicle != nil
                appliedORVScan = nil
                if vehicle == nil {
                    syncNicknameIfNeeded()
                }
            }
            .onChange(of: brand) { _, _ in
                syncNicknameIfNeeded()
            }
            .onChange(of: model) { _, _ in
                syncNicknameIfNeeded()
            }
            .onChange(of: nickname) { _, newValue in
                guard !isSyncingNickname else { return }
                let trimmed = newValue.trimmingCharacters(in: .whitespacesAndNewlines)
                if trimmed.isEmpty {
                    hasManualNicknameOverride = false
                    syncNicknameIfNeeded()
                    return
                }
                let suggested = suggestedNickname()
                if suggested.isEmpty {
                    hasManualNicknameOverride = true
                    return
                }
                hasManualNicknameOverride = trimmed.caseInsensitiveCompare(suggested) != .orderedSame
            }
        }
    }

    private func decodeVIN() async {
        guard let token = env.authManager.token else { return }
        let vinValue = VehicleInputValidator.normalizedVIN(vin)
        if let validationMessage = VehicleInputValidator.validationMessage(for: vin, required: true) {
            vinLookupError = validationMessage
            return
        }

        isLookingUpVIN = true
        vinLookupMessage = nil
        vinLookupError = nil
        defer { isLookingUpVIN = false }

        do {
            let decoded = try await vehicleService.decodeVINDetailed(vinValue, token: token)
            if decoded.success, let data = decoded.data {
                vin = data.vin ?? vinValue
                if let make = data.make, !make.isEmpty { brand = make }
                if let modelValue = data.model, !modelValue.isEmpty { model = modelValue }
                if let yearValue = data.productionYear ?? data.modelYear { year = String(yearValue) }

                if let displacement = data.engineDisplacementCc, let power = data.enginePowerKw {
                    engine = "\(displacement) cm3 / \(power) kW"
                } else if let code = data.engineCode, !code.isEmpty {
                    engine = code
                }

                if let stk = data.stkValidUntil ?? data.techInspectionValidTo, let parsed = parseDate(stk) {
                    stkDate = parsed
                    vinLookupMessage = "VIN dekódováno a platnost STK aktualizována."
                } else {
                    vinLookupMessage = "VIN dekódováno, ale platnost STK se nepodařilo určit."
                }
                return
            }

            // Fallback na původní endpoint pro případ, že detailní dekodér nevrátí data.
            let response = try await vehicleService.lookupVIN(vinValue, token: token)
            vin = response.vin
            if let make = response.make, !make.isEmpty { brand = make }
            if let modelValue = response.model, !modelValue.isEmpty { model = modelValue }
            if let yearValue = response.year { year = String(yearValue) }
            if let engineValue = response.engine, !engineValue.isEmpty { engine = engineValue }

            if let detail = response.detail, !detail.isEmpty {
                vinLookupMessage = detail
            } else {
                vinLookupMessage = "VIN dekódováno ze zdroje: \(response.source)."
            }
        } catch {
            vinLookupError = error.localizedDescription
        }
    }

    private func decodePlate() async {
        guard let token = env.authManager.token else { return }
        let plateValue = plate.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        guard !plateValue.isEmpty else { return }

        isLookingUpVIN = true
        vinLookupMessage = nil
        vinLookupError = nil
        defer { isLookingUpVIN = false }

        do {
            let decoded = try await vehicleService.decodePlate(plateValue, token: token)
            guard decoded.success, let data = decoded.data else {
                vinLookupError = decoded.errors.first ?? "Dekódování SPZ se nezdařilo."
                return
            }
            plate = data.plate ?? plateValue
            if let vinValue = data.vin, !vinValue.isEmpty { vin = vinValue }
            if let make = data.make, !make.isEmpty { brand = make }
            if let modelValue = data.model, !modelValue.isEmpty { model = modelValue }
            if let yearValue = data.productionYear ?? data.modelYear { year = String(yearValue) }
            if let displacement = data.engineDisplacementCc, let power = data.enginePowerKw {
                engine = "\(displacement) cm3 / \(power) kW"
            } else if let code = data.engineCode, !code.isEmpty {
                engine = code
            }
            if let stk = data.stkValidUntil ?? data.techInspectionValidTo, let parsed = parseDate(stk) {
                stkDate = parsed
            }
            vinLookupMessage = "Data vozidla načtena podle SPZ."
        } catch {
            vinLookupError = error.localizedDescription
        }
    }

    private func startTachometerLookup() async {
        guard let token = env.authManager.token else { return }
        let vinValue = VehicleInputValidator.normalizedVIN(vin)
        if VehicleInputValidator.validationMessage(for: vin, required: true) != nil {
            vinLookupError = "Pro kontrolu tachometru zadejte validní VIN."
            return
        }

        isLookingUpTachometer = true
        vinLookupMessage = nil
        vinLookupError = nil
        defer { isLookingUpTachometer = false }

        do {
            if let vehicle {
                let response = try await vehicleService.initVehicleTachometer(vehicleId: vehicle.id, token: token)
                tachometerChallenge = TachometerChallengeResponse(
                    challengeId: response.sessionId,
                    captchaImageBase64: response.captchaImageBase64,
                    captchaMimeType: response.captchaMimeType,
                    expiresInSeconds: response.expiresInSeconds
                )
            } else {
                tachometerChallenge = try await vehicleService.createTachometerChallenge(vin: vinValue, token: token)
            }
            showTachometerCaptchaSheet = true
        } catch {
            vinLookupError = friendlyTachometerError(from: error)
        }
    }

    private func submitTachometerLookup(captchaCode: String) async {
        guard let token = env.authManager.token else { return }
        guard let challenge = tachometerChallenge else {
            vinLookupError = "Captcha challenge vypršel. Zkuste načíst nový obrázek."
            return
        }

        let vinValue = VehicleInputValidator.normalizedVIN(vin)
        let code = captchaCode.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !code.isEmpty else {
            vinLookupError = "Zadejte captcha kód z obrázku."
            return
        }

        isLookingUpTachometer = true
        vinLookupMessage = nil
        vinLookupError = nil
        defer { isLookingUpTachometer = false }

        do {
            if let vehicle {
                let response = try await vehicleService.submitVehicleTachometer(
                    vehicleId: vehicle.id,
                    sessionId: challenge.challengeId,
                    captchaCode: code,
                    token: token
                )
                currentMileageKm = response.vehicle.currentMileageKm.map(String.init) ?? currentMileageKm
                lastStkMileageKm = response.vehicle.lastStkMileageKm.map(String.init) ?? String(response.latestMileageKm)
                let formatted = formatMileage(response.latestMileageKm)
                vinLookupMessage = "Načten a uložen poslední stav km ze STK/emisí: \(formatted) km."
            } else {
                let response = try await vehicleService.lookupTachometer(
                    challengeId: challenge.challengeId,
                    vin: vinValue,
                    captchaCode: code,
                    token: token
                )

                let formatted = formatMileage(response.latestMileageKm)
                lastStkMileageKm = String(response.latestMileageKm)
                vinLookupMessage = "Načten poslední stav km ze STK/emisí: \(formatted) km."
            }
            showTachometerCaptchaSheet = false
            tachometerChallenge = nil
        } catch {
            vinLookupError = friendlyTachometerError(from: error)
            if shouldResetTachometerChallenge(after: error) {
                showTachometerCaptchaSheet = false
                tachometerChallenge = nil
            }
        }
    }

    private func shouldResetTachometerChallenge(after error: Error) -> Bool {
        let lowered = error.localizedDescription.lowercased()
        return lowered.contains("vypršel")
            || lowered.contains("neplatný")
            || lowered.contains("jinému vozidlu")
    }

    private func submitVehicle() async {
        isSubmitting = true
        submitError = nil
        defer { isSubmitting = false }

        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd"

        do {
            try await onSubmit(
                VehicleCreateRequest(
                    nickname: nickname,
                    brand: brand.isEmpty ? nil : brand,
                    model: model.isEmpty ? nil : model,
                    year: Int(year),
                    engine: engine.isEmpty ? nil : engine,
                    vin: normalizedCurrentVIN.isEmpty ? nil : normalizedCurrentVIN,
                    plate: plate.isEmpty ? nil : plate,
                    notes: notes.isEmpty ? nil : notes,
                    stkValidUntil: formatter.string(from: stkDate),
                    currentMileageKm: parsedCurrentMileageKm,
                    lastStkMileageKm: parsedLastStkMileageKm,
                    tyresInfo: vehicle?.tyresInfo,
                    insuranceProvider: vehicle?.insuranceProvider,
                    insuranceValidUntil: nil,
                    orvScanId: appliedORVScan?.scanId,
                    orvNumber: appliedORVScan?.vehicleFields.orvNumber,
                    orvUseOwnerData: appliedORVScan?.includeOwnerData,
                    dataTrustState: appliedORVScan?.persistedTrustState
                )
            )
            dismiss()
        } catch {
            submitError = error.localizedDescription
        }
    }

    private func friendlyTachometerError(from error: Error) -> String {
        let message = error.localizedDescription.trimmingCharacters(in: .whitespacesAndNewlines)
        let lowered = message.lowercased()
        if lowered == "not found" || lowered.contains("404") || lowered.contains("not found") {
            let baseURL = APIClient.configuredBaseURLString()
            return "Aktuální server (\(baseURL)) ještě neumí Kontrolu tachometru. V Xcode přepněte aplikaci na backend, kde jsou aktivní endpointy /api/v1/vehicles/tachometer/*."
        }
        return message
    }

    private func parseDate(_ value: String) -> Date? {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }

        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = iso.date(from: trimmed) { return d }
        iso.formatOptions = [.withInternetDateTime]
        if let d = iso.date(from: trimmed) { return d }

        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        for format in [
            "yyyy-MM-dd",
            "dd.MM.yyyy",
            "dd/MM/yyyy",
            "yyyy-MM-dd'T'HH:mm:ss",
            "yyyy-MM-dd'T'HH:mm:ss.SSS",
            "yyyy-MM-dd'T'HH:mm:ssZ",
            "yyyy-MM-dd'T'HH:mm:ss.SSSZ"
        ] {
            formatter.dateFormat = format
            if let d = formatter.date(from: trimmed) { return d }
        }
        return nil
    }

    private func parseMileageInput(_ raw: String) -> Int? {
        let normalized = raw
            .replacingOccurrences(of: " ", with: "")
            .replacingOccurrences(of: ".", with: "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !normalized.isEmpty else { return nil }
        return Int(normalized)
    }

    private func formatMileage(_ value: Int) -> String {
        let formatter = NumberFormatter()
        formatter.locale = Locale(identifier: "cs_CZ")
        formatter.numberStyle = .decimal
        formatter.groupingSeparator = " "
        return formatter.string(from: NSNumber(value: value)) ?? String(value)
    }

    private func suggestedNickname() -> String {
        [brand, model]
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .joined(separator: " ")
    }

    private func syncNicknameIfNeeded() {
        guard !hasManualNicknameOverride else { return }
        let suggested = suggestedNickname()
        guard !suggested.isEmpty else { return }
        isSyncingNickname = true
        nickname = suggested
        isSyncingNickname = false
    }

    private func applyORVScanResult(_ result: ORVScanReviewResult) {
        appliedORVScan = result
        let normalizedVIN = VehicleInputValidator.normalizedVIN(result.vehicleFields.vin)
        if !normalizedVIN.isEmpty {
            vin = normalizedVIN
        }
        let normalizedPlate = result.vehicleFields.plate.trimmingCharacters(in: .whitespacesAndNewlines)
        if !normalizedPlate.isEmpty {
            let value = normalizedPlate
            plate = value.uppercased()
        }
        let normalizedBrand = result.vehicleFields.brand.trimmingCharacters(in: .whitespacesAndNewlines)
        if !normalizedBrand.isEmpty {
            let value = normalizedBrand
            brand = value
        }
        let normalizedModel = result.vehicleFields.model.trimmingCharacters(in: .whitespacesAndNewlines)
        if !normalizedModel.isEmpty {
            let value = normalizedModel
            model = value
        }
        let engineParts = [result.vehicleFields.engineDisplacementCc, result.vehicleFields.enginePowerKw]
            .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        if !engineParts.isEmpty {
            engine = engineParts.joined(separator: " / ")
        }
        vinLookupError = nil
        vinLookupMessage = "Údaje z ORV byly převzaty do formuláře. Vozidlo uložíte až tlačítkem Uložit."
        syncNicknameIfNeeded()
    }
}

enum ORVScanFlowState: String {
    case idle
    case capturingFront
    case frontCaptured
    case capturingBack
    case backCaptured
    case processing
    case review
    case confirmed
    case failed
}

enum ORVProcessingStage {
    case uploading
    case processing

    var title: String {
        switch self {
        case .uploading:
            return "Nahrávám doklad..."
        case .processing:
            return "Zpracovávám údaje z ORV..."
        }
    }

    var detail: String {
        switch self {
        case .uploading:
            return "Připravuji menší přílohy a odesílám obě strany na server."
        case .processing:
            return "Probíhá OCR, kontrola VIN/RZ a příprava review kroku."
        }
    }
}

struct ORVEditableVehicleFields {
    var plate: String = ""
    var vin: String = ""
    var brand: String = ""
    var model: String = ""
    var typeLabel: String = ""
    var fuel: String = ""
    var enginePowerKw: String = ""
    var engineDisplacementCc: String = ""
    var firstRegistrationDate: String = ""
    var category: String = ""
    var orvNumber: String = ""

    init() {}

    init(parsed: ORVParsedVehicleFields) {
        plate = parsed.plate ?? ""
        vin = parsed.vin ?? ""
        brand = parsed.brand ?? ""
        model = parsed.model ?? ""
        typeLabel = parsed.typeLabel ?? ""
        fuel = parsed.fuel ?? ""
        enginePowerKw = parsed.enginePowerKw ?? ""
        engineDisplacementCc = parsed.engineDisplacementCc ?? ""
        firstRegistrationDate = parsed.firstRegistrationDate ?? parsed.firstRegistrationCzDate ?? ""
        category = parsed.category ?? ""
        orvNumber = parsed.orvNumber ?? ""
    }
}

struct ORVEditableOwnerFields {
    var ownerName: String = ""
    var ownerIdentifier: String = ""
    var ownerAddress: String = ""
    var operatorName: String = ""
    var operatorIdentifier: String = ""
    var operatorAddress: String = ""

    init() {}

    init(parsed: ORVParsedOwnerFields) {
        ownerName = parsed.ownerName ?? ""
        ownerIdentifier = parsed.ownerIdentifier ?? ""
        ownerAddress = parsed.ownerAddress ?? ""
        operatorName = parsed.operatorName ?? ""
        operatorIdentifier = parsed.operatorIdentifier ?? ""
        operatorAddress = parsed.operatorAddress ?? ""
    }
}

struct ORVScanReviewResult {
    let scanId: Int
    let trustState: String
    let vehicleFields: ORVEditableVehicleFields
    let ownerFields: ORVEditableOwnerFields
    let includeOwnerData: Bool
    let warnings: [String]
    let confidence: [ORVFieldConfidence]

    private var normalizedBackendTrustState: String {
        let normalized = trustState.trimmingCharacters(in: .whitespacesAndNewlines)
        return normalized.isEmpty ? "scanned_unverified" : normalized
    }

    var backendTrustStateLabel: String {
        Self.trustStateLabel(for: normalizedBackendTrustState)
    }

    var reviewTrustState: String {
        switch normalizedBackendTrustState {
        case "verified_by_service":
            return "verified_by_service"
        case "verified_by_user":
            return "verified_by_user"
        case "scanned_reviewed":
            return "scanned_reviewed"
        default:
            return "scanned_reviewed"
        }
    }

    var reviewTrustStateLabel: String {
        Self.trustStateLabel(for: reviewTrustState)
    }

    var persistedTrustState: String {
        switch normalizedBackendTrustState {
        case "verified_by_service":
            return "verified_by_service"
        case "verified_by_user":
            return "verified_by_user"
        default:
            return "verified_by_user"
        }
    }

    var persistedTrustStateLabel: String {
        Self.trustStateLabel(for: persistedTrustState)
    }

    var trustStateLabel: String {
        reviewTrustStateLabel
    }

    private static func trustStateLabel(for state: String) -> String {
        switch state {
        case "verified_by_user":
            return "Ověřeno uživatelem"
        case "scanned_reviewed":
            return "Zkontrolováno po scanu"
        case "scanned_unverified":
            return "Naskenováno, neověřeno"
        case "verified_by_service":
            return "Ověřeno servisem"
        default:
            return state
        }
    }
}

struct ORVScanFlowSheet: View {
    let onConfirm: (ORVScanReviewResult) -> Void

    @EnvironmentObject private var env: AppEnvironment
    @Environment(\.dismiss) private var dismiss
    @State private var flowState: ORVScanFlowState = .idle
    @State private var frontImage: UIImage?
    @State private var backImage: UIImage?
    @State private var frontData: Data?
    @State private var backData: Data?
    @State private var showFrontScanner = false
    @State private var showBackScanner = false
    @State private var vehicleFields = ORVEditableVehicleFields()
    @State private var ownerFields = ORVEditableOwnerFields()
    @State private var includeOwnerData = false
    @State private var confidence: [ORVFieldConfidence] = []
    @State private var warnings: [String] = []
    @State private var missingFields: [String] = []
    @State private var scanId: Int?
    @State private var trustState = "scanned_unverified"
    @State private var errorMessage: String?
    @State private var processingStage: ORVProcessingStage = .uploading

    private let vehicleService = VehicleService(api: APIClient())
    private var reviewVINError: String? {
        VehicleInputValidator.validationMessage(for: vehicleFields.vin, required: true)
    }

    var body: some View {
        NavigationStack {
            Group {
                switch flowState {
                case .idle, .capturingFront, .frontCaptured, .capturingBack, .backCaptured, .failed:
                    introView
                case .processing:
                    processingView
                case .review, .confirmed:
                    reviewView
                }
            }
            .navigationTitle("Sken ORV")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Zavřít") { dismiss() }
                }
            }
            .sheet(isPresented: $showFrontScanner) {
                ORVSingleSideScanner { image, data in
                    frontImage = image
                    frontData = data
                    flowState = .frontCaptured
                    showFrontScanner = false
                } onCancel: {
                    showFrontScanner = false
                    if flowState == .capturingFront { flowState = .idle }
                }
            }
            .sheet(isPresented: $showBackScanner) {
                ORVSingleSideScanner { image, data in
                    backImage = image
                    backData = data
                    flowState = .backCaptured
                    showBackScanner = false
                    Task { await processScanIfReady() }
                } onCancel: {
                    showBackScanner = false
                    if flowState == .capturingBack { flowState = .frontCaptured }
                }
            }
        }
    }

    private var introView: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Spacing.lg) {
                Text(flowState == .frontCaptured ? "Naskenujte zadní stranu ORV." : "Naskenujte přední stranu ORV.")
                    .font(Theme.Typography.sectionTitle)
                    .foregroundStyle(Theme.Colors.textPrimary)
                VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                    Text("• celý doklad musí být v rámečku")
                    Text("• bez odlesků")
                    Text("• čitelný text")
                    Text("• bez obou stran nelze pokračovat")
                }
                .font(Theme.Typography.body)
                .foregroundStyle(Theme.Colors.textSecondary)

                if let image = frontImage {
                    orvPreviewCard(title: "Přední strana", image: image)
                }
                if let image = backImage {
                    orvPreviewCard(title: "Zadní strana", image: image)
                }
                if let errorMessage {
                    Text(errorMessage)
                        .font(Theme.Typography.caption)
                        .foregroundStyle(.red)
                }

                VStack(spacing: Theme.Spacing.md) {
                    if flowState == .failed, frontData != nil, backData != nil {
                        Button("Zkusit znovu zpracování") {
                            Task { await processScanIfReady() }
                        }
                        .buttonStyle(.borderedProminent)
                    }
                    if flowState == .frontCaptured || flowState == .backCaptured || backImage != nil {
                        Button("Zopakovat přední stranu") {
                            flowState = .capturingFront
                            showFrontScanner = true
                        }
                        .buttonStyle(.bordered)
                    }
                    if flowState == .frontCaptured || frontImage != nil {
                        Button(backImage == nil ? "Naskenovat zadní stranu" : "Zopakovat zadní stranu") {
                            flowState = .capturingBack
                            showBackScanner = true
                        }
                        .buttonStyle(.borderedProminent)
                    } else {
                        Button("Naskenovat přední stranu") {
                            flowState = .capturingFront
                            showFrontScanner = true
                        }
                        .buttonStyle(.borderedProminent)
                    }
                }
            }
            .padding(Theme.Spacing.lg)
        }
    }

    private var processingView: some View {
        VStack(spacing: Theme.Spacing.lg) {
            ProgressView()
                .progressViewStyle(.circular)
            Text(processingStage.title)
                .font(Theme.Typography.sectionTitle)
            Text(processingStage.detail)
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colors.textSecondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(Theme.Spacing.lg)
    }

    private var reviewView: some View {
        Form {
            Section("Údaje vozidla") {
                TextField("RZ / SPZ", text: $vehicleFields.plate)
                    .textInputAutocapitalization(.characters)
                    .autocorrectionDisabled(true)
                TextField("VIN", text: $vehicleFields.vin)
                    .textInputAutocapitalization(.characters)
                    .autocorrectionDisabled(true)
                TextField("Značka", text: $vehicleFields.brand)
                TextField("Model", text: $vehicleFields.model)
                TextField("Typ", text: $vehicleFields.typeLabel)
                TextField("Palivo", text: $vehicleFields.fuel)
                TextField("Výkon", text: $vehicleFields.enginePowerKw)
                TextField("Objem", text: $vehicleFields.engineDisplacementCc)
                TextField("Datum první registrace", text: $vehicleFields.firstRegistrationDate)
                TextField("Kategorie", text: $vehicleFields.category)
                TextField("Číslo ORV", text: $vehicleFields.orvNumber)
            }

            Section("Údaje vlastníka / provozovatele") {
                Toggle("Při finálním uložení označit použití osobních údajů z ORV", isOn: $includeOwnerData)
                Text("Tyto údaje se do formuláře vozidla nepřenášejí. Do finálního uložení odešlete pouze ORV scan a svou volbu, zda mají být osobní údaje z dokladu použité.")
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Colors.textSecondary)
                orvReadOnlyField(title: "Vlastník", value: ownerFields.ownerName)
                orvReadOnlyField(title: "Datum narození / IČO vlastníka", value: ownerFields.ownerIdentifier)
                orvReadOnlyField(title: "Adresa vlastníka", value: ownerFields.ownerAddress)
                orvReadOnlyField(title: "Provozovatel", value: ownerFields.operatorName)
                orvReadOnlyField(title: "Datum narození / IČO provozovatele", value: ownerFields.operatorIdentifier)
                orvReadOnlyField(title: "Adresa provozovatele", value: ownerFields.operatorAddress)
            }

            Section("Stav extrakce") {
                ForEach(confidence, id: \.fieldName) { item in
                    HStack {
                        Text(localizedFieldLabel(item.fieldName))
                        Spacer()
                        Text(item.state == "high" ? "Jisté" : item.state == "missing" ? "Chybí" : "Zkontrolovat")
                            .foregroundStyle(item.state == "high" ? Theme.Colors.accent : (item.state == "missing" ? .red : .orange))
                    }
                }
                ForEach(warnings, id: \.self) { warning in
                    Text(warning)
                        .foregroundStyle(.orange)
                }
                if !missingFields.isEmpty {
                    Text("Chybí: \(missingFields.map(localizedFieldLabel).joined(separator: ", "))")
                        .foregroundStyle(.red)
                }
            }

            Section {
                Text("Upravené údaje vozidla se po potvrzení přenesou do předchozího formuláře. Vozidlo se ještě neukládá.")
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Colors.textSecondary)
                Text("Backend scan: \(ORVScanReviewResult(scanId: scanId ?? 0, trustState: trustState, vehicleFields: vehicleFields, ownerFields: ownerFields, includeOwnerData: includeOwnerData, warnings: warnings, confidence: confidence).backendTrustStateLabel)")
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Colors.textSecondary)
                Text("Po potvrzení review v aplikaci: \(ORVScanReviewResult(scanId: scanId ?? 0, trustState: trustState, vehicleFields: vehicleFields, ownerFields: ownerFields, includeOwnerData: includeOwnerData, warnings: warnings, confidence: confidence).reviewTrustStateLabel)")
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Colors.textSecondary)
                Button("Zopakovat scan") {
                    resetAll()
                }
                .buttonStyle(.bordered)
                Button("Použít údaje v formuláři") {
                    guard let scanId else { return }
                    flowState = .confirmed
                    onConfirm(
                        ORVScanReviewResult(
                            scanId: scanId,
                            trustState: trustState,
                            vehicleFields: vehicleFields,
                            ownerFields: ownerFields,
                            includeOwnerData: includeOwnerData,
                            warnings: warnings,
                            confidence: confidence
                        )
                    )
                }
                .disabled(reviewVINError != nil)
            }

            if let reviewVINError {
                Section {
                    Text(reviewVINError)
                        .foregroundStyle(.red)
                }
            }
        }
    }

    @ViewBuilder
    private func orvPreviewCard(title: String, image: UIImage) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            Text(title)
                .font(Theme.Typography.body)
                .foregroundStyle(Theme.Colors.textPrimary)
            Image(uiImage: image)
                .resizable()
                .scaledToFit()
                .frame(maxWidth: .infinity)
                .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.md))
        }
        .padding(Theme.Spacing.md)
        .background(
            RoundedRectangle(cornerRadius: Theme.Radius.lg)
                .fill(Theme.Colors.surface)
        )
    }

    private func processScanIfReady() async {
        guard let token = env.authManager.token,
              let frontData,
              let backData else {
            flowState = .failed
            errorMessage = "Pro zpracování jsou nutné obě strany ORV."
            return
        }
        flowState = .processing
        errorMessage = nil
        do {
            processingStage = .uploading
            let frontImageBase64 = frontData.base64EncodedString()
            let backImageBase64 = backData.base64EncodedString()
            processingStage = .processing
            let response = try await vehicleService.parseORV(
                ORVParseRequest(
                    frontImageBase64: frontImageBase64,
                    backImageBase64: backImageBase64,
                    frontImageMimeType: "image/jpeg",
                    backImageMimeType: "image/jpeg",
                    source: "ios_orv_scan"
                ),
                token: token
            )
            scanId = response.scanId
            trustState = response.trustState
            vehicleFields = ORVEditableVehicleFields(parsed: response.vehicleFields)
            ownerFields = ORVEditableOwnerFields(parsed: response.ownerFields)
            confidence = response.confidence
            warnings = response.warnings
            missingFields = response.missingFields
            flowState = .review
        } catch {
            errorMessage = localizedORVProcessingError(from: error)
            flowState = .failed
        }
    }

    private func resetAll() {
        flowState = .idle
        frontImage = nil
        backImage = nil
        frontData = nil
        backData = nil
        vehicleFields = ORVEditableVehicleFields()
        ownerFields = ORVEditableOwnerFields()
        includeOwnerData = false
        confidence = []
        warnings = []
        missingFields = []
        scanId = nil
        trustState = "scanned_unverified"
        errorMessage = nil
        processingStage = .uploading
    }

    private func localizedORVProcessingError(from error: Error) -> String {
        let message = error.localizedDescription.trimmingCharacters(in: .whitespacesAndNewlines)
        let lowered = message.lowercased()
        if lowered.contains("timed out")
            || lowered.contains("čas vypršel")
            || lowered.contains("trvalo příliš dlouho")
        {
            return "Zpracování ORV trvalo příliš dlouho. Zkuste to znovu."
        }
        if lowered.contains("offline")
            || lowered.contains("internet")
            || lowered.contains("network")
            || lowered.contains("spojení")
            || lowered.contains("nelze se připojit")
            || lowered.contains("could not connect")
            || lowered.contains("not connected")
        {
            return "Nepodařilo se připojit k serveru."
        }
        if lowered.contains("ocr")
            || lowered.contains("nepodařilo se přečíst")
            || lowered.contains("nepodařilo se zpracovat obsah")
            || lowered.contains("nelze rozpoznat")
            || lowered.contains("doklad")
            || lowered.contains("parse")
        {
            return "Doklad se nepodařilo správně přečíst."
        }
        return "Nepodařilo se dokončit zpracování ORV."
    }

    private func localizedFieldLabel(_ fieldName: String) -> String {
        switch fieldName {
        case "vin": return "VIN"
        case "plate": return "RZ / SPZ"
        case "orv_number": return "Číslo ORV"
        case "brand": return "Značka"
        case "model": return "Model"
        case "owner_name": return "Vlastník"
        default: return fieldName
        }
    }

    @ViewBuilder
    private func orvReadOnlyField(title: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
            Text(title)
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colors.textSecondary)
            Text(value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "Neuvedeno" : value)
                .font(Theme.Typography.body)
                .foregroundStyle(Theme.Colors.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.vertical, 2)
    }
}

struct ORVSingleSideScanner: UIViewControllerRepresentable {
    let onComplete: (UIImage, Data) -> Void
    let onCancel: () -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(onComplete: onComplete, onCancel: onCancel)
    }

    func makeUIViewController(context: Context) -> VNDocumentCameraViewController {
        let controller = VNDocumentCameraViewController()
        controller.delegate = context.coordinator
        return controller
    }

    func updateUIViewController(_ uiViewController: VNDocumentCameraViewController, context: Context) {}

    final class Coordinator: NSObject, VNDocumentCameraViewControllerDelegate {
        let onComplete: (UIImage, Data) -> Void
        let onCancel: () -> Void

        init(onComplete: @escaping (UIImage, Data) -> Void, onCancel: @escaping () -> Void) {
            self.onComplete = onComplete
            self.onCancel = onCancel
        }

        func documentCameraViewControllerDidCancel(_ controller: VNDocumentCameraViewController) {
            controller.dismiss(animated: true)
            onCancel()
        }

        func documentCameraViewController(_ controller: VNDocumentCameraViewController, didFailWithError error: Error) {
            controller.dismiss(animated: true)
            onCancel()
        }

        func documentCameraViewController(_ controller: VNDocumentCameraViewController, didFinishWith scan: VNDocumentCameraScan) {
            guard scan.pageCount > 0 else {
                controller.dismiss(animated: true)
                onCancel()
                return
            }
            let image = scan.imageOfPage(at: 0)
            let normalized = normalizedImage(from: image)
            let prepared = optimizedORVUpload(from: normalized)
            controller.dismiss(animated: true) {
                self.onComplete(prepared.previewImage, prepared.data)
            }
        }

        private func normalizedImage(from image: UIImage) -> UIImage {
            guard image.imageOrientation != .up else { return image }
            let renderer = UIGraphicsImageRenderer(size: image.size)
            return renderer.image { _ in
                image.draw(in: CGRect(origin: .zero, size: image.size))
            }
        }

        private func optimizedORVUpload(from image: UIImage) -> (previewImage: UIImage, data: Data) {
            let maxLongEdge: CGFloat = 1800
            let maxBytes = 1_600_000
            let resized = resizedImageIfNeeded(image, maxLongEdge: maxLongEdge)
            var compression: CGFloat = 0.82
            var data = resized.jpegData(compressionQuality: compression) ?? Data()
            while data.count > maxBytes, compression > 0.5 {
                compression -= 0.08
                data = resized.jpegData(compressionQuality: compression) ?? data
            }
            return (resized, data)
        }

        private func resizedImageIfNeeded(_ image: UIImage, maxLongEdge: CGFloat) -> UIImage {
            let size = image.size
            let longEdge = max(size.width, size.height)
            guard longEdge > maxLongEdge, longEdge > 0 else { return image }
            let scale = maxLongEdge / longEdge
            let targetSize = CGSize(width: floor(size.width * scale), height: floor(size.height * scale))
            let format = UIGraphicsImageRendererFormat.default()
            format.opaque = true
            let renderer = UIGraphicsImageRenderer(size: targetSize, format: format)
            return renderer.image { _ in
                image.draw(in: CGRect(origin: .zero, size: targetSize))
            }
        }
    }
}
