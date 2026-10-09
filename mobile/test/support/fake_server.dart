import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/misc.dart';
import 'package:ludifun/core/offline.dart';
import 'package:ludifun/core/api/ludifun_api.dart';
import 'package:ludifun/core/link_opener.dart';
import 'package:ludifun/core/session.dart';
import 'package:ludifun/core/sounds.dart';
import 'package:ludifun/core/storage/credentials.dart';
import 'package:ludifun/features/lesson/resource_screen.dart';

import 'fakes.dart';

typedef Reply = (int status, Object? body);
typedef Handler = FutureOr<Reply> Function(RequestOptions request);

/// Faux serveur branché sous dio : une réponse par « MÉTHODE /chemin ».
class FakeServer implements HttpClientAdapter {
  final handlers = <String, Handler>{};
  final requests = <RequestOptions>[];

  /// Corps envoyés (multipart compris), dans l'ordre des requêtes.
  final bodies = <Uint8List>[];

  /// En-têtes de réponse supplémentaires, par route.
  final headers = <String, Map<String, String>>{};

  void on(String route, Handler handler, {Map<String, String> headers = const {}}) {
    handlers[route] = handler;
    this.headers[route] = headers;
  }

  /// Plus de réseau : chaque requête échoue comme sans Internet.
  bool offline = false;

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
    if (offline) {
      throw DioException(requestOptions: options, type: DioExceptionType.connectionError);
    }
    final chunks = requestStream == null ? const <Uint8List>[] : await requestStream.toList();
    bodies.add(Uint8List.fromList([for (final chunk in chunks) ...chunk]));
    final route = '${options.method} ${options.path}';
    final handler = handlers[route];
    final (status, body) = handler == null
        ? error(404, 'not_found', 'Introuvable.')
        : await handler(options);
    if (body is Uint8List) {
      return ResponseBody.fromBytes(
        body,
        status,
        headers: {
          Headers.contentTypeHeader: ['image/png'],
        },
      );
    }
    return ResponseBody.fromString(
      body == null ? '' : jsonEncode(body),
      status,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
        for (final MapEntry(:key, :value) in (headers[route] ?? const {}).entries) key: [value],
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

/// Pages ouvertes dans le navigateur (politique de confidentialité…).
class FakeLinkOpener implements LinkOpener {
  final opened = <Uri>[];

  @override
  Future<bool> open(Uri uri) async {
    opened.add(uri);
    return true;
  }
}

/// Sons joués pendant les tests, sans lecteur audio.
class FakeSoundPlayer implements SoundPlayer {
  final played = <Sound>[];

  @override
  Future<void> play(Sound sound) async => played.add(sound);
}

List<Override> overridesFor(
  FakeServer server,
  CredentialStore store, [
  LinkOpener? links,
  OfflineStore? offline,
  FakeSoundPlayer? sounds,
]) => [
  soundPlayerProvider.overrideWithValue(sounds ?? FakeSoundPlayer()),
  soundSettingStoreProvider.overrideWithValue(MemorySoundSettingStore()),
  credentialStoreProvider.overrideWithValue(store),
  linkOpenerProvider.overrideWithValue(links ?? FakeLinkOpener()),
  bareDioProvider.overrideWithValue(buildDio('http://api.test')..httpClientAdapter = server),
  resourcePageProvider.overrideWithValue(const FakeResourcePage()),
  offlineStoreProvider.overrideWithValue(offline ?? MemoryOfflineStore()),
];

Duration? noRetry(int _, Object _) => null;
