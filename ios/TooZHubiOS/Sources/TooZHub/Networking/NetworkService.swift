import Foundation

protocol NetworkService {
    func request<T: Decodable>(_ endpoint: APIEndpoint, token: String?) async throws -> T
    func requestNoContent(_ endpoint: APIEndpoint, token: String?) async throws
    func requestData(_ endpoint: APIEndpoint, token: String?) async throws -> Data
}
