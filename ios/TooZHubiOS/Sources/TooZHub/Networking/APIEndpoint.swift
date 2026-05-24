import Foundation

enum HTTPMethod: String {
    case get = "GET"
    case post = "POST"
    case put = "PUT"
    case delete = "DELETE"
}

struct APIEndpoint {
    let path: String
    let method: HTTPMethod
    var queryItems: [URLQueryItem] = []
    var body: Data? = nil
    var timeoutInterval: TimeInterval? = nil

    static func get(_ path: String, queryItems: [URLQueryItem] = [], timeoutInterval: TimeInterval? = nil) -> APIEndpoint {
        APIEndpoint(path: path, method: .get, queryItems: queryItems, timeoutInterval: timeoutInterval)
    }

    static func post(_ path: String, body: Data? = nil, timeoutInterval: TimeInterval? = nil) -> APIEndpoint {
        APIEndpoint(path: path, method: .post, body: body, timeoutInterval: timeoutInterval)
    }

    static func put(_ path: String, body: Data? = nil, timeoutInterval: TimeInterval? = nil) -> APIEndpoint {
        APIEndpoint(path: path, method: .put, body: body, timeoutInterval: timeoutInterval)
    }

    static func delete(_ path: String, body: Data? = nil, timeoutInterval: TimeInterval? = nil) -> APIEndpoint {
        APIEndpoint(path: path, method: .delete, body: body, timeoutInterval: timeoutInterval)
    }
}
