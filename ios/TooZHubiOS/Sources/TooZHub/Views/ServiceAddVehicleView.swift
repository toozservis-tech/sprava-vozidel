import SwiftUI
import UIKit

private struct ServiceTachometerCaptchaSheet: View {
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
            VStack(spacing: Theme.Spacing.lg) {
                Text("Ověření tachometru")
                    .font(Theme.Typography.sectionTitle)
                    .foregroundStyle(Theme.Colors.textPrimary)

                if let captchaImage {
                    Image(uiImage: captchaImage)
                        .resizable()
                        .scaledToFit()
                        .frame(maxHeight: 100)
                        .padding(.horizontal, Theme.Spacing.md)
                        .background(
                            RoundedRectangle(cornerRadius: Theme.Radius.md)
                                .fill(Theme.Colors.surface)
                        )
                } else {
                    Text("Captcha obrázek se nepodařilo načíst.")
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colors.textSecondary)
                }

                TextField("Kód z obrázku", text: $captchaCode)
                    .textInputAutocapitalization(.characters)
                    .autocorrectionDisabled(true)
                    .padding(.horizontal, Theme.Spacing.md)
                    .padding(.vertical, Theme.Spacing.sm)
                    .background(
                        RoundedRectangle(cornerRadius: Theme.Radius.md)
                            .fill(Theme.Colors.surface)
                    )

                if let errorMessage, !errorMessage.isEmpty {
                    Text(errorMessage)
                        .font(Theme.Typography.caption)
                        .foregroundStyle(.red)
                }

                HStack(spacing: Theme.Spacing.md) {
                    Button("Zrušit", role: .cancel, action: onCancel)
                        .buttonStyle(.bordered)

                    Button {
                        onSubmit(captchaCode)
                    } label: {
                        if isSubmitting {
                            ProgressView()
                                .progressViewStyle(.circular)
                        } else {
                            Text("Načíst km")
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(captchaCode.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSubmitting)
                }
            }
            .padding(Theme.Spacing.lg)
            .navigationTitle("Kontrola tachometru")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}

struct ServiceAddVehicleView: View {
    private enum AssignmentMode: String, CaseIterable, Identifiable {
        case linkedCustomer
        case inviteOwner

        var id: String { rawValue }

        var title: String {
            switch self {
            case .linkedCustomer:
                return "Existující klient"
            case .inviteOwner:
                return "Pozvat majitele"
            }
        }
    }

    @EnvironmentObject private var env: AppEnvironment
    @State private var customers: [ServiceWorkspaceCustomer] = []
    @State private var selectedCustomerId: Int = 0
    @State private var assignmentMode: AssignmentMode = .linkedCustomer
    @State private var inviteEmail = ""
    @State private var inviteName = ""
    @State private var inviteMessage = ""
    @State private var nickname = ""
    @State private var brand = ""
    @State private var model = ""
    @State private var year = ""
    @State private var plate = ""
    @State private var vin = ""
    @State private var currentMileageKm = ""
    @State private var lastStkMileageKm = ""
    @State private var stkDate = Date().addingTimeInterval(60 * 60 * 24 * 365)
    @State private var message: String?
    @State private var vinInfo: String?
    @State private var isLoading = false
    @State private var vinLoading = false
    @State private var isLookingUpTachometer = false
    @State private var tachometerChallenge: TachometerChallengeResponse?
    @State private var showTachometerCaptchaSheet = false
    @State private var hasManualNicknameOverride = false
    @State private var isSyncingNickname = false
    @State private var showORVScanFlow = false
    @State private var appliedORVScan: ORVScanReviewResult?

    private let service = ServiceWorkspaceService(api: APIClient())
    private let vehicleService = VehicleService(api: APIClient())
    private var parsedCurrentMileageKm: Int? { parseMileageInput(currentMileageKm) }
    private var parsedLastStkMileageKm: Int? { parseMileageInput(lastStkMileageKm) }
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

    private var isInviteMode: Bool {
        assignmentMode == .inviteOwner
    }

    private var inviteEmailError: String? {
        guard isInviteMode else { return nil }
        let trimmed = inviteEmail.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return "Vyplňte e-mail budoucího vlastníka." }
        return trimmed.contains("@") ? nil : "E-mail budoucího vlastníka není ve správném formátu."
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
                        VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                            Text("Údaje z ORV jsou připravené ve formuláři")
                                .font(Theme.Typography.captionStrong)
                                .foregroundStyle(Theme.Colors.textPrimary)
                            Text("Po kontrole v aplikaci: \(appliedORVScan.reviewTrustStateLabel)")
                                .font(Theme.Typography.caption)
                                .foregroundStyle(Theme.Colors.textSecondary)
                            Text("Při finálním přidání vozidla se scan uloží jako: \(appliedORVScan.persistedTrustStateLabel)")
                                .font(Theme.Typography.caption)
                                .foregroundStyle(Theme.Colors.textSecondary)
                            Text("Vozidlo klientovi přidáte až tlačítkem Přidat vozidlo klientovi.")
                                .font(Theme.Typography.caption)
                                .foregroundStyle(Theme.Colors.textSecondary)
                        }
                    }
                }
                Section("Klient") {
                    Picker("Režim", selection: $assignmentMode) {
                        ForEach(AssignmentMode.allCases) { mode in
                            Text(mode.title).tag(mode)
                        }
                    }

                    if isInviteMode {
                        TextField("E-mail budoucího vlastníka", text: $inviteEmail)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled(true)
                            .keyboardType(.emailAddress)
                        TextField("Jméno majitele", text: $inviteName)
                        TextField("Zpráva do pozvánky", text: $inviteMessage, axis: .vertical)
                            .lineLimit(2...4)
                    } else {
                        Picker("Vyberte klienta", selection: $selectedCustomerId) {
                            ForEach(customers) { customer in
                                Text(customer.name ?? customer.email).tag(customer.customerId)
                            }
                        }
                    }
                }

                Section("Vozidlo") {
                    HStack {
                        TextField("VIN", text: $vin)
                            .textInputAutocapitalization(.characters)
                            .autocorrectionDisabled(true)
                        Button("Načíst") {
                            Task { await decodeVIN() }
                        }
                        .disabled(vinLoading || !VehicleInputValidator.isValidVIN(vin))
                    }
                    TextField("Název", text: $nickname)
                    TextField("Značka", text: $brand)
                    TextField("Model", text: $model)
                    TextField("Rok výroby", text: $year)
                        .keyboardType(.numberPad)
                    HStack {
                        TextField("SPZ", text: $plate)
                            .textInputAutocapitalization(.characters)
                            .autocorrectionDisabled(true)
                        Button("Načíst") {
                            Task { await decodePlate() }
                        }
                        .disabled(vinLoading || plate.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }
                    DatePicker("Platnost STK", selection: $stkDate, displayedComponents: .date)
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
                                    .progressViewStyle(.circular)
                            }
                            Text("Načíst poslední km z Kontroly tachometru")
                        }
                    }
                    .disabled(
                        isLookingUpTachometer ||
                        !VehicleInputValidator.isValidVIN(vin)
                    )
                }

                if let vinInfo {
                    Section {
                        Text(vinInfo)
                            .font(Theme.Typography.caption)
                            .foregroundStyle(Theme.Colors.accent)
                    }
                }

                if let mileageValidationError {
                    Section {
                        Text(mileageValidationError)
                            .font(Theme.Typography.caption)
                            .foregroundStyle(.red)
                    }
                }
                if let orvValidationError {
                    Section {
                        Text(orvValidationError)
                            .font(Theme.Typography.caption)
                            .foregroundStyle(.red)
                    }
                }
                if let inviteEmailError {
                    Section {
                        Text(inviteEmailError)
                            .font(Theme.Typography.caption)
                            .foregroundStyle(.red)
                    }
                }

                if let message {
                    Section {
                        Text(message)
                            .font(Theme.Typography.caption)
                    }
                }

                Section {
                    Button(isInviteMode ? "Zařadit vozidlo a poslat pozvánku" : "Přidat vozidlo klientovi") {
                        Task { await submit() }
                    }
                    .disabled(
                        isLoading ||
                        (!isInviteMode && selectedCustomerId == 0) ||
                        nickname.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ||
                        (isInviteMode && inviteEmailError != nil) ||
                        mileageValidationError != nil ||
                        orvValidationError != nil
                    )
                }
            }
            .navigationTitle("Přidat vozidlo")
            .task { await loadCustomers() }
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
            .sheet(isPresented: $showTachometerCaptchaSheet) {
                if let challenge = tachometerChallenge {
                    ServiceTachometerCaptchaSheet(
                        challenge: challenge,
                        isSubmitting: isLookingUpTachometer,
                        errorMessage: message,
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
        }
    }

    private func loadCustomers() async {
        guard let token = env.authManager.token else { return }
        do {
            customers = try await service.fetchCustomers(token: token)
            selectedCustomerId = customers.first?.customerId ?? 0
            if customers.isEmpty {
                assignmentMode = .inviteOwner
            }
        } catch {
            customers = []
            assignmentMode = .inviteOwner
            message = UserFacingErrorMapper.message(
                for: error,
                context: .account,
                fallback: "Seznam klientů se nepodařilo načíst. Můžete ale zaevidovat vozidlo a pozvat budoucího majitele."
            )
        }
    }

    private func submit() async {
        guard let token = env.authManager.token else { return }
        isLoading = true
        defer { isLoading = false }

        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd"

        do {
            let vehicleRequest = ServiceWorkspaceVehicleCreateRequest(
                nickname: nickname,
                brand: brand.isEmpty ? nil : brand,
                model: model.isEmpty ? nil : model,
                year: Int(year),
                plate: plate.isEmpty ? nil : plate,
                vin: VehicleInputValidator.normalizedVIN(vin).nilIfBlank,
                stkValidUntil: formatter.string(from: stkDate),
                currentMileageKm: parsedCurrentMileageKm,
                lastStkMileageKm: parsedLastStkMileageKm,
                engine: nil,
                notes: nil,
                orvScanId: appliedORVScan?.scanId,
                orvNumber: appliedORVScan?.vehicleFields.orvNumber.nilIfBlank,
                orvUseOwnerData: appliedORVScan?.includeOwnerData,
                dataTrustState: appliedORVScan?.persistedTrustState
            )

            if isInviteMode {
                let response = try await service.createPendingVehicleRegistration(
                    PendingVehicleRegistrationRequest(
                        inviteEmail: inviteEmail.trimmingCharacters(in: .whitespacesAndNewlines),
                        inviteName: inviteName.nilIfBlank,
                        inviteMessage: inviteMessage.nilIfBlank,
                        vehicle: vehicleRequest
                    ),
                    token: token
                )
                message = response.message ?? "Vozidlo bylo zaevidováno a pozvánka připravena."
            } else {
                try await service.createCustomerVehicle(
                    customerId: selectedCustomerId,
                    request: vehicleRequest,
                    token: token
                )
                message = "Vozidlo bylo úspěšně přidáno."
            }

            nickname = ""
            brand = ""
            model = ""
            year = ""
            plate = ""
            vin = ""
            currentMileageKm = ""
            lastStkMileageKm = ""
            hasManualNicknameOverride = false
            appliedORVScan = nil
            inviteName = ""
            inviteMessage = ""
        } catch {
            message = UserFacingErrorMapper.message(
                for: error,
                context: .account,
                fallback: isInviteMode
                    ? "Vozidlo se nepodařilo zaevidovat a pozvánku odeslat."
                    : "Vozidlo se nepodařilo přidat klientovi."
            )
        }
    }

    private func decodeVIN() async {
        guard let token = env.authManager.token else { return }
        let vinValue = VehicleInputValidator.normalizedVIN(vin)
        if let validationMessage = VehicleInputValidator.validationMessage(for: vin, required: true) {
            message = validationMessage
            return
        }

        vinLoading = true
        message = nil
        vinInfo = nil
        defer { vinLoading = false }

        do {
            let decoded = try await vehicleService.decodeVINDetailed(vinValue, token: token)
            if decoded.success, let data = decoded.data {
                vin = data.vin ?? vinValue
                if let make = data.make, !make.isEmpty { brand = make }
                if let modelValue = data.model, !modelValue.isEmpty { model = modelValue }
                if let yearValue = data.productionYear ?? data.modelYear { year = String(yearValue) }

                if let displacement = data.engineDisplacementCc, let power = data.enginePowerKw {
                    vinInfo = "Motor: \(displacement) cm3 / \(power) kW"
                } else if let code = data.engineCode, !code.isEmpty {
                    vinInfo = "Motor: \(code)"
                } else {
                    vinInfo = "VIN dekódováno."
                }

                if let stk = data.stkValidUntil ?? data.techInspectionValidTo, let parsed = parseDate(stk) {
                    stkDate = parsed
                    vinInfo = "\(vinInfo ?? "VIN dekódováno.") STK aktualizována."
                }
                return
            }

            // Fallback na původní VIN endpoint, pokud detailní dekodér nevrátí data.
            let fallback = try await vehicleService.lookupVIN(vinValue, token: token)
            vin = fallback.vin
            if let make = fallback.make, !make.isEmpty { brand = make }
            if let modelValue = fallback.model, !modelValue.isEmpty { model = modelValue }
            if let yearValue = fallback.year { year = String(yearValue) }
            if let engine = fallback.engine, !engine.isEmpty {
                vinInfo = "Motor: \(engine)"
            } else {
                vinInfo = "VIN dekódováno (\(fallback.source))."
            }
        } catch {
            message = error.localizedDescription
        }
    }

    private func decodePlate() async {
        guard let token = env.authManager.token else { return }
        let plateValue = plate.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        guard !plateValue.isEmpty else { return }

        vinLoading = true
        message = nil
        vinInfo = nil
        defer { vinLoading = false }

        do {
            let decoded = try await vehicleService.decodePlate(plateValue, token: token)
            guard decoded.success, let data = decoded.data else {
                message = decoded.errors.first ?? "Dekódování SPZ se nezdařilo."
                return
            }
            plate = data.plate ?? plateValue
            if let vinValue = data.vin, !vinValue.isEmpty { vin = vinValue }
            if let make = data.make, !make.isEmpty { brand = make }
            if let modelValue = data.model, !modelValue.isEmpty { model = modelValue }
            if let yearValue = data.productionYear ?? data.modelYear { year = String(yearValue) }
            if let displacement = data.engineDisplacementCc, let power = data.enginePowerKw {
                vinInfo = "Motor: \(displacement) cm3 / \(power) kW"
            } else if let code = data.engineCode, !code.isEmpty {
                vinInfo = "Motor: \(code)"
            } else {
                vinInfo = "Data vozidla načtena podle SPZ."
            }
            if let stk = data.stkValidUntil ?? data.techInspectionValidTo, let parsed = parseDate(stk) {
                stkDate = parsed
            }
        } catch {
            message = error.localizedDescription
        }
    }

    private func startTachometerLookup() async {
        guard let token = env.authManager.token else { return }
        message = nil
        let normalizedVin = VehicleInputValidator.normalizedVIN(vin)
        if VehicleInputValidator.validationMessage(for: vin, required: true) != nil {
            message = "VIN musí být validní, aby šlo načíst STK tachometr."
            return
        }

        isLookingUpTachometer = true
        defer { isLookingUpTachometer = false }

        do {
            tachometerChallenge = try await vehicleService.createTachometerChallenge(vin: normalizedVin, token: token)
            showTachometerCaptchaSheet = true
        } catch {
            message = friendlyTachometerError(from: error)
        }
    }

    private func submitTachometerLookup(captchaCode: String) async {
        guard let token = env.authManager.token else { return }
        guard let challenge = tachometerChallenge else {
            message = "Captcha challenge vypršela, načtěte ji znovu."
            return
        }

        let code = captchaCode.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !code.isEmpty else {
            message = "Zadejte captcha kód z obrázku."
            return
        }

        isLookingUpTachometer = true
        defer { isLookingUpTachometer = false }

        do {
            let response = try await vehicleService.lookupTachometer(
                challengeId: challenge.challengeId,
                vin: vin,
                captchaCode: code,
                token: token
            )
            lastStkMileageKm = String(response.latestMileageKm)
            let checkDateText = response.latestCheckDate
                .map { date in
                    let formatter = DateFormatter()
                    formatter.locale = Locale(identifier: "cs_CZ")
                    formatter.dateStyle = .medium
                    formatter.timeStyle = .none
                    return formatter.string(from: date)
                } ?? "neznámé datum"
            message = "Poslední údaj STK načten: \(formatMileage(response.latestMileageKm)) km (\(checkDateText))."
            showTachometerCaptchaSheet = false
            tachometerChallenge = nil
        } catch {
            message = friendlyTachometerError(from: error)
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

    private func friendlyTachometerError(from error: Error) -> String {
        let message = error.localizedDescription.trimmingCharacters(in: .whitespacesAndNewlines)
        let lowered = message.lowercased()
        if lowered == "not found" || lowered.contains("404") || lowered.contains("not found") {
            let baseURL = APIClient.configuredBaseURLString()
            return "Aktuální server (\(baseURL)) ještě neumí Kontrolu tachometru. V Xcode přepněte aplikaci na backend, kde jsou aktivní endpointy /api/v1/vehicles/tachometer/*."
        }
        return message
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
        if let value = result.vehicleFields.vin.nilIfBlank {
            vin = VehicleInputValidator.normalizedVIN(value)
        }
        if let value = result.vehicleFields.plate.nilIfBlank {
            plate = value.uppercased()
        }
        if let value = result.vehicleFields.brand.nilIfBlank {
            brand = value
        }
        if let value = result.vehicleFields.model.nilIfBlank {
            model = value
        }
        message = "Údaje z ORV byly převzaty do formuláře. Vozidlo klientovi přidáte až tlačítkem Přidat vozidlo klientovi."
        syncNicknameIfNeeded()
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
}

private extension String {
    var nilIfBlank: String? {
        let trimmed = trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}
