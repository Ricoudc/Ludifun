import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/misc.dart';
import 'package:ludifun/core/api/ludifun_api.dart';
import 'package:ludifun/core/session.dart';
import 'package:ludifun/core/storage/credentials.dart';

typedef Reply = (int status, Object? body);
typedef Handler = FutureOr<Reply> Function(RequestOptions request);

/// Faux serveur branché sous dio : une réponse par « MÉTHODE /chemin ».
class FakeServer implements HttpClientAdapter {
  final handlers = <String, Handler>{};
  final requests = <RequestOptions>[];

  void on(String route, Handler handler) => handlers[route] = handler;

  List<String> get routes => [for (final r in requests) '${r.method} ${r.path}'];

  static Reply error(int status, String code, String message) => (
    status,
    {
      'error': {'code': code, 'message': message},
    },
  );

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options);
    final handler = handlers['${options.method} ${options.path}'];
    final (status, body) = handler == null
        ? error(404, 'not_found', 'Introuvable.')
        : await handler(options);
    return ResponseBody.fromString(
      body == null ? '' : jsonEncode(body),
      status,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

String? bearer(RequestOptions request) => request.headers['Authorization'] as String?;

Map<String, Object?> tokens(String access, String refresh) => {
  'access_token': access,
  'refresh_token': refresh,
  'token_type': 'bearer',
  'expires_in': 900,
  'parent': {'id': 'p1', 'email': 'parent@example.fr'},
};

const emma = {'id': 'c1', 'display_name': 'Emma', 'grade': 'CM1', 'avatar': null};

List<Override> overridesFor(FakeServer server, CredentialStore store) => [
  credentialStoreProvider.overrideWithValue(store),
  bareDioProvider.overrideWithValue(buildDio('http://api.test')..httpClientAdapter = server),
];

Duration? noRetry(int _, Object _) => null;
