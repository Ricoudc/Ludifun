import 'package:dio/dio.dart';

/// Erreur de l'API (§11.3) ou du réseau, avec un message affichable tel quel.
class ApiException implements Exception {
  const ApiException(this.code, this.message, {this.status});

  factory ApiException.fromDio(DioException error) {
    switch (error.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
        return const ApiException('timeout', 'Le serveur met trop de temps à répondre. Réessaie.');
      case DioExceptionType.connectionError:
        return const ApiException('network', 'Pas de connexion. Vérifie Internet et réessaie.');
      default:
        break;
    }
    final response = error.response;
    if (response == null) {
      return const ApiException('network', 'Pas de connexion. Vérifie Internet et réessaie.');
    }
    final body = response.data;
    if (body is Map && body['error'] is Map) {
      final detail = body['error'] as Map;
      return ApiException(
        detail['code'] as String? ?? 'error',
        detail['message'] as String? ?? unexpected,
        status: response.statusCode,
      );
    }
    return ApiException('http_${response.statusCode}', unexpected, status: response.statusCode);
  }

  static const unexpected = 'Petit souci de notre côté, réessaie.';

  final String code;
  final String message;
  final int? status;

  @override
  String toString() => 'ApiException($code, $status): $message';
}
