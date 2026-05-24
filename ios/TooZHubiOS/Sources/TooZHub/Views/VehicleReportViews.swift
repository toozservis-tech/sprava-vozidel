import SwiftUI
import PDFKit

struct VehicleReportSheet: View {
    let vehicleId: Int
    let vehicleName: String

    @EnvironmentObject private var env: AppEnvironment
    @Environment(\.dismiss) private var dismiss

    @State private var pdfURL: URL?
    @State private var errorMessage: String?
    @State private var isLoadingPDF = false
    @State private var showPDFPreview = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Spacing.lg) {
                    summaryCard
                    reportActionsCard
                }
                .padding(Theme.Spacing.md)
                .padding(.bottom, Theme.Spacing.xxl)
            }
            .background(Theme.Colors.background.ignoresSafeArea())
            .navigationTitle("Report vozidla")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Zavřít") { dismiss() }
                }
            }
            .sheet(isPresented: $showPDFPreview) {
                if let pdfURL {
                    NavigationStack {
                        VehiclePDFPreviewScreen(url: pdfURL)
                    }
                }
            }
        }
    }

    private var summaryCard: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            Text(vehicleName)
                .font(Theme.Typography.headline)
                .foregroundStyle(.white)

            metadataRow("Zdroj", value: "Backend PDF export")
            Text("Tento checkout podporuje pouze stažení PDF servisní historie vozidla. Veřejné verify odkazy ani report modes zde backend neposkytuje.")
                .font(Theme.Typography.caption)
                .foregroundStyle(Theme.Colors.textSecondary)

            if let errorMessage, !errorMessage.isEmpty {
                Text(errorMessage)
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Colors.danger)
            }
        }
        .hubDarkCard()
    }

    private var reportActionsCard: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            SectionHeader(title: "PDF report", subtitle: "Stažení, preview a sdílení PDF servisní historie z backendu")

            Button {
                Task { await downloadPDF() }
            } label: {
                HStack(spacing: Theme.Spacing.sm) {
                    if isLoadingPDF {
                        ProgressView()
                    }
                    Text("Stáhnout a otevřít PDF report")
                }
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(PrimaryActionButtonStyle())
            .disabled(isLoadingPDF)

            if let pdfURL {
                HStack(spacing: Theme.Spacing.sm) {
                    Button("Preview PDF") {
                        showPDFPreview = true
                    }
                    .buttonStyle(InlineChipButtonStyle(isSelected: true))

                    ShareLink(item: pdfURL) {
                        Text("Sdílet PDF")
                            .font(Theme.Typography.captionStrong)
                    }
                    .buttonStyle(InlineChipButtonStyle(isSelected: false))
                }
            }
        }
        .hubDarkCard()
    }

    private func metadataRow(_ title: String, value: String) -> some View {
        HStack(alignment: .top, spacing: Theme.Spacing.sm) {
            Text(title)
                .font(Theme.Typography.tiny)
                .foregroundStyle(Theme.Colors.textSecondary)
                .frame(width: 96, alignment: .leading)
            Text(value)
                .font(Theme.Typography.caption)
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity, alignment: .leading)
                .textSelection(.enabled)
        }
    }

    private func downloadPDF() async {
        guard let token = env.authManager.token else { return }
        isLoadingPDF = true
        errorMessage = nil
        defer { isLoadingPDF = false }

        do {
            pdfURL = try await env.vehicleService.downloadVehicleReportPDF(vehicleId: vehicleId, token: token)
            showPDFPreview = true
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct VehiclePDFPreviewScreen: View {
    let url: URL

    var body: some View {
        PDFKitView(url: url)
            .background(Color.white.ignoresSafeArea())
            .navigationTitle("PDF preview")
            .navigationBarTitleDisplayMode(.inline)
    }
}

private struct PDFKitView: UIViewRepresentable {
    let url: URL

    func makeUIView(context: Context) -> PDFView {
        let view = PDFView()
        view.autoScales = true
        view.displayDirection = .vertical
        view.backgroundColor = .white
        return view
    }

    func updateUIView(_ uiView: PDFView, context: Context) {
        if uiView.document?.documentURL != url {
            uiView.document = PDFDocument(url: url)
        }
    }
}
