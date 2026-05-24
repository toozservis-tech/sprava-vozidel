import SwiftUI
import UIKit
import AVFoundation

enum VehicleCardMode: String, CaseIterable, Identifiable {
    case grid
    case list
    case compact

    var id: String { rawValue }

    var title: String {
        switch self {
        case .grid:
            return "Mřížka"
        case .list:
            return "Seznam"
        case .compact:
            return "Kompaktní"
        }
    }

    var icon: String {
        switch self {
        case .grid:
            return "square.grid.2x2"
        case .list:
            return "list.bullet"
        case .compact:
            return "rectangle.compress.vertical"
        }
    }
}

struct VehicleBrandVisualStyle {
    let accent: Color
    let background: Color

    static func resolve(for vehicle: Vehicle) -> VehicleBrandVisualStyle {
        switch vehicle.normalizedBrandKey {
        case "skoda":
            return .init(accent: Color(red: 0.06, green: 0.58, blue: 0.33), background: Color(red: 0.89, green: 0.97, blue: 0.92))
        case "audi":
            return .init(accent: Color(red: 0.15, green: 0.19, blue: 0.25), background: Color(red: 0.92, green: 0.94, blue: 0.97))
        case "bmw":
            return .init(accent: Color(red: 0.14, green: 0.42, blue: 0.88), background: Color(red: 0.90, green: 0.95, blue: 1.00))
        case "mercedesbenz", "mercedes":
            return .init(accent: Color(red: 0.21, green: 0.28, blue: 0.34), background: Color(red: 0.92, green: 0.95, blue: 0.97))
        case "volkswagen", "vw":
            return .init(accent: Color(red: 0.00, green: 0.36, blue: 0.71), background: Color(red: 0.89, green: 0.95, blue: 1.00))
        case "ford":
            return .init(accent: Color(red: 0.05, green: 0.31, blue: 0.66), background: Color(red: 0.90, green: 0.94, blue: 1.00))
        case "toyota":
            return .init(accent: Color(red: 0.84, green: 0.16, blue: 0.21), background: Color(red: 1.00, green: 0.92, blue: 0.93))
        case "hyundai":
            return .init(accent: Color(red: 0.05, green: 0.34, blue: 0.69), background: Color(red: 0.91, green: 0.95, blue: 1.00))
        case "kia":
            return .init(accent: Color(red: 0.70, green: 0.12, blue: 0.14), background: Color(red: 1.00, green: 0.92, blue: 0.92))
        case "tesla":
            return .init(accent: Color(red: 0.80, green: 0.12, blue: 0.19), background: Color(red: 1.00, green: 0.92, blue: 0.93))
        default:
            return .init(accent: Theme.Colors.primary, background: Theme.Colors.warningSoft)
        }
    }
}

struct VehicleBrandBadge: View {
    let vehicle: Vehicle
    var compact: Bool = false

    private var style: VehicleBrandVisualStyle {
        .resolve(for: vehicle)
    }

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: compact ? 12 : 16, style: .continuous)
                .fill(style.background)
            Text(vehicle.brandMonogram)
                .font(.system(size: compact ? 14 : 18, weight: .bold))
                .foregroundStyle(style.accent)
        }
        .frame(width: compact ? 34 : 52, height: compact ? 34 : 52)
        .overlay(
            RoundedRectangle(cornerRadius: compact ? 12 : 16, style: .continuous)
                .stroke(style.accent.opacity(0.14), lineWidth: 1)
        )
    }
}

struct VehiclePhotoPlaceholderView: View {
    let vehicle: Vehicle
    var compact: Bool = false

    private var style: VehicleBrandVisualStyle {
        .resolve(for: vehicle)
    }

    var body: some View {
        ZStack(alignment: .topLeading) {
            RoundedRectangle(cornerRadius: compact ? 16 : 20, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [style.background, Color.white],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )

            VStack(alignment: .leading, spacing: compact ? 6 : 10) {
                VehicleBrandBadge(vehicle: vehicle, compact: compact)
                Spacer(minLength: 0)
                Image(systemName: "car.side.fill")
                    .font(.system(size: compact ? 24 : 34, weight: .semibold))
                    .foregroundStyle(style.accent.opacity(0.9))
                Text(vehicle.brand?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false ? vehicle.brand! : "Bez fotky")
                    .font(compact ? Theme.Typography.tiny : Theme.Typography.captionStrong)
                    .foregroundStyle(Theme.Colors.textOnLightSecondary)
                    .lineLimit(1)
            }
            .padding(compact ? Theme.Spacing.sm : Theme.Spacing.md)
        }
    }
}

@MainActor
final class VehiclePhotoLoader: ObservableObject {
    @Published private(set) var image: UIImage?
    @Published private(set) var isLoading = false

    private let service = VehicleService(api: APIClient())
    private var loadedVehicleId: Int?
    private var loadedPhotoPath: String?
    private var loadedToken: String?

    func load(vehicle: Vehicle, token: String?) async {
        guard vehicle.hasUserPhoto else {
            image = nil
            loadedVehicleId = vehicle.id
            loadedPhotoPath = vehicle.photoPath
            loadedToken = token
            return
        }
        guard let token, !token.isEmpty else { return }
        guard loadedVehicleId != vehicle.id || loadedPhotoPath != vehicle.photoPath || loadedToken != token || image == nil else {
            return
        }

        isLoading = true
        defer { isLoading = false }

        do {
            let data = try await service.fetchVehiclePhotoData(vehicleId: vehicle.id, token: token)
            image = UIImage(data: data)
            loadedVehicleId = vehicle.id
            loadedPhotoPath = vehicle.photoPath
            loadedToken = token
        } catch {
            image = nil
        }
    }

    func reset() {
        image = nil
        loadedVehicleId = nil
        loadedPhotoPath = nil
        loadedToken = nil
    }
}

struct AuthenticatedVehiclePhotoView<Placeholder: View>: View {
    let vehicle: Vehicle
    let height: CGFloat
    let cornerRadius: CGFloat
    let imageHorizontalOffset: CGFloat
    let placeholder: Placeholder

    @EnvironmentObject private var env: AppEnvironment
    @StateObject private var loader = VehiclePhotoLoader()

    init(
        vehicle: Vehicle,
        height: CGFloat,
        cornerRadius: CGFloat = 20,
        imageHorizontalOffset: CGFloat = 0,
        @ViewBuilder placeholder: () -> Placeholder
    ) {
        self.vehicle = vehicle
        self.height = height
        self.cornerRadius = cornerRadius
        self.imageHorizontalOffset = imageHorizontalOffset
        self.placeholder = placeholder()
    }

    var body: some View {
        ZStack {
            if let image = loader.image {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFill()
                    .offset(x: imageHorizontalOffset)
                    .transition(.opacity)
            } else {
                placeholder
                    .overlay {
                        if loader.isLoading {
                            ProgressView()
                        }
                    }
            }
        }
        .frame(maxWidth: .infinity)
        .frame(height: height)
        .clipped()
        .clipShape(RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
        .task(id: "\(vehicle.id)-\(vehicle.photoPath ?? "")-\(env.authManager.token ?? "")") {
            await loader.load(vehicle: vehicle, token: env.authManager.token)
        }
    }
}

struct VehiclePhotoCropperSheet: View {
    let image: UIImage
    let onCommit: (UIImage) -> Void
    let onFallback: (UIImage) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var zoom: CGFloat = 1
    @State private var lastZoom: CGFloat = 1
    @State private var offset: CGSize = .zero
    @State private var lastOffset: CGSize = .zero
    @State private var renderError: String?

    private let cropAspectRatio: CGFloat = 16.0 / 9.0
    private let outputSize = CGSize(width: 1280, height: 720)

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: Theme.Spacing.md) {
                Text("Upravte výřez fotky vozidla do poměru 16:9. Pokud editor selže nebo nechcete upravovat ručně, použijte bezpečný fallback.")
                    .font(Theme.Typography.caption)
                    .foregroundStyle(Theme.Colors.textSecondary)

                GeometryReader { geometry in
                    let width = geometry.size.width
                    let height = width / cropAspectRatio
                    let cropSize = CGSize(width: width, height: min(height, geometry.size.height))

                    ZStack {
                        RoundedRectangle(cornerRadius: 20, style: .continuous)
                            .fill(Theme.Colors.surface)

                        Image(uiImage: image)
                            .resizable()
                            .scaledToFill()
                            .scaleEffect(zoom)
                            .offset(offset)
                            .frame(width: cropSize.width, height: cropSize.height)
                            .clipped()
                            .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
                            .gesture(
                                SimultaneousGesture(
                                    MagnificationGesture()
                                        .onChanged { value in
                                            zoom = min(max(lastZoom * value, 1), 4)
                                        }
                                        .onEnded { _ in
                                            lastZoom = zoom
                                        },
                                    DragGesture()
                                        .onChanged { value in
                                            offset = CGSize(
                                                width: lastOffset.width + value.translation.width,
                                                height: lastOffset.height + value.translation.height
                                            )
                                        }
                                        .onEnded { _ in
                                            lastOffset = offset
                                        }
                                )
                            )

                        RoundedRectangle(cornerRadius: 20, style: .continuous)
                            .stroke(Color.white.opacity(0.75), lineWidth: 1.5)
                    }
                    .frame(width: cropSize.width, height: cropSize.height)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
                }
                .frame(height: 260)

                HStack(spacing: Theme.Spacing.sm) {
                    Button("Reset") {
                        zoom = 1
                        lastZoom = 1
                        offset = .zero
                        lastOffset = .zero
                        renderError = nil
                    }
                    .buttonStyle(InlineChipButtonStyle(isSelected: false))

                    Button("Fallback bez editoru") {
                        onFallback(fallbackImage())
                        dismiss()
                    }
                    .buttonStyle(InlineChipButtonStyle(isSelected: false))
                }

                if let renderError, !renderError.isEmpty {
                    Text(renderError)
                        .font(Theme.Typography.caption)
                        .foregroundStyle(Theme.Colors.danger)
                }

                Spacer(minLength: 0)
            }
            .padding(Theme.Spacing.md)
            .background(Theme.Colors.background.ignoresSafeArea())
            .navigationTitle("Ořez fotky")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Zrušit") {
                        dismiss()
                    }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Použít") {
                        guard let cropped = renderCroppedImage() else {
                            renderError = "Interaktivní editor selhal. Použijte fallback režim."
                            return
                        }
                        onCommit(cropped)
                        dismiss()
                    }
                }
            }
        }
    }

    private func fallbackImage() -> UIImage {
        let fitted = imageByCenterCropping(image: image, targetSize: outputSize)
        return fitted ?? image
    }

    private func renderCroppedImage() -> UIImage? {
        guard let fitted = imageByCenterCropping(image: image, targetSize: outputSize) else { return nil }
        let renderer = UIGraphicsImageRenderer(size: outputSize)
        let rendered = renderer.image { context in
            UIColor.black.setFill()
            context.fill(CGRect(origin: .zero, size: outputSize))

            let baseRect = AVMakeRect(aspectRatio: fitted.size, insideRect: CGRect(origin: .zero, size: outputSize))
            let centeredRect = CGRect(
                x: baseRect.origin.x + offset.width * 2.2 - ((baseRect.width * zoom) - baseRect.width) / 2,
                y: baseRect.origin.y + offset.height * 2.2 - ((baseRect.height * zoom) - baseRect.height) / 2,
                width: baseRect.width * zoom,
                height: baseRect.height * zoom
            )
            fitted.draw(in: centeredRect)
        }
        return rendered
    }

    private func imageByCenterCropping(image: UIImage, targetSize: CGSize) -> UIImage? {
        let renderer = UIGraphicsImageRenderer(size: targetSize)
        return renderer.image { _ in
            let rect = AVMakeRect(aspectRatio: image.size, insideRect: CGRect(origin: .zero, size: targetSize))
            let fillScale = max(targetSize.width / rect.width, targetSize.height / rect.height)
            let drawSize = CGSize(width: rect.width * fillScale, height: rect.height * fillScale)
            let drawRect = CGRect(
                x: (targetSize.width - drawSize.width) / 2,
                y: (targetSize.height - drawSize.height) / 2,
                width: drawSize.width,
                height: drawSize.height
            )
            image.draw(in: drawRect)
        }
    }
}

struct VehiclePhotoCameraPicker: UIViewControllerRepresentable {
    let onImage: (UIImage) -> Void
    let onCancel: () -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(onImage: onImage, onCancel: onCancel)
    }

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let controller = UIImagePickerController()
        controller.sourceType = .camera
        controller.cameraCaptureMode = .photo
        controller.delegate = context.coordinator
        controller.modalPresentationStyle = .fullScreen
        return controller
    }

    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}

    final class Coordinator: NSObject, UINavigationControllerDelegate, UIImagePickerControllerDelegate {
        private let onImage: (UIImage) -> Void
        private let onCancel: () -> Void

        init(onImage: @escaping (UIImage) -> Void, onCancel: @escaping () -> Void) {
            self.onImage = onImage
            self.onCancel = onCancel
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            picker.dismiss(animated: true)
            onCancel()
        }

        func imagePickerController(
            _ picker: UIImagePickerController,
            didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]
        ) {
            let image = (info[.editedImage] ?? info[.originalImage]) as? UIImage
            picker.dismiss(animated: true) {
                if let image {
                    self.onImage(image)
                } else {
                    self.onCancel()
                }
            }
        }
    }
}
