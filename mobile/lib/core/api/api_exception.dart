import 'dart:convert';

import 'package:dio/dio.dart';

/// Erreur de l'API (§11.3) ou du réseau, avec un message affichable tel quel.
class ApiException implements Exception {
  const ApiException(this.code, this.message, {this.status, this.serverCategory});

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
    final body = _json(response.data);
    if (body is Map && body['error'] is Map) {
      final detail = body['error'] as Map;
      return ApiException(
        detail['code'] as String? ?? 'error',
        detail['message'] as String? ?? unexpected,
        status: response.statusCode,
        serverCategory: detail['category'] as String?,
      );
    }
    return ApiException('http_${response.statusCode}', unexpected, status: response.statusCode);
  }

  static const unexpected = 'Petit souci de notre côté, réessaie.';

  /// Corps d'erreur déjà décodé, ou reçu en octets (téléchargement de fichier).
  static Object? _json(Object? data) {
    if (data is! List<int>) return data;
    try {
      return jsonDecode(utf8.decode(data));
    } on FormatException {
      return null;
    }
  }

  final String code;
  final String message;
  final int? status;

  /// Catégorie envoyée par le serveur (absente avec un ancien serveur).
  final String? serverCategory;

  /// Catégorie du cahier des charges (§135) : donnée par le serveur, sinon déduite ici
  /// (`NETWORK_ERROR` et `TIMEOUT` n'existent que du côté de l'application).
  String get category =>
      serverCategory ??
      switch ((code, status)) {
        ('network', _) => 'NETWORK_ERROR',
        ('timeout', _) => 'TIMEOUT',
        (_, 401 || 403) => 'AUTH_ERROR',
        (_, 429) => 'RATE_LIMIT',
        (_, 400 || 413 || 415 || 422) => 'VALIDATION_ERROR',
        (_, 404 || 409) => 'USER_ERROR',
        _ => 'UNKNOWN_ERROR',
      };

  @override
  String toString() => 'ApiException($code, $status): $message';
}
