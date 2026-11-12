import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Qui utilise cet appareil : personne encore, un parent connecté, ou un enfant
/// dont l'appareil a été lié par son parent. Un appareil sert un seul espace.
sealed class Credentials {
  const Credentials();

  Map<String, String> toJson();

  static Credentials fromJson(Map<String, dynamic> json) => switch (json) {
    {
      'space': 'parent',
      'access_token': final String access,
      'refresh_token': final String refresh,
      'email': final String email,
    } =>
      ParentCredentials(accessToken: access, refreshToken: refresh, email: email),
    {
      'space': 'child',
      'device_token': final String token,
      'child_id': final String childId,
      'display_name': final String name,
    } =>
      ChildCredentials(deviceToken: token, childId: childId, displayName: name),
    _ => const NoCredentials(),
  };
}

class NoCredentials extends Credentials {
  const NoCredentials();

  @override
  Map<String, String> toJson() => const {};
}

class ParentCredentials extends Credentials {
  const ParentCredentials({
    required this.accessToken,
    required this.refreshToken,
    required this.email,
  });

  final String accessToken;
  final String refreshToken;
  final String email;

  @override
  Map<String, String> toJson() => {
    'space': 'parent',
    'access_token': accessToken,
    'refresh_token': refreshToken,
    'email': email,
  };
}

class ChildCredentials extends Credentials {
  const ChildCredentials({
    required this.deviceToken,
    required this.childId,
    required this.displayName,
  });

  final String deviceToken;
  final String childId;
  final String displayName;

  @override
  Map<String, String> toJson() => {
    'space': 'child',
    'device_token': deviceToken,
    'child_id': childId,
    'display_name': displayName,
  };
}

abstract interface class CredentialStore {
  Future<Credentials> read();
  Future<void> write(Credentials credentials);
}

/// Jetons dans le stockage chiffré du système (Keychain, Keystore) : §16.1.
class SecureCredentialStore implements CredentialStore {
  SecureCredentialStore([FlutterSecureStorage? storage])
    : _storage = storage ?? const FlutterSecureStorage();

  static const key = 'ludifun.credentials';
  final FlutterSecureStorage _storage;

  @override
  Future<Credentials> read() async {
    final raw = await _storage.read(key: key);
    if (raw == null) return const NoCredentials();
    try {
      return Credentials.fromJson(jsonDecode(raw) as Map<String, dynamic>);
    } on FormatException {
      return const NoCredentials();
    } on TypeError {
      return const NoCredentials();
    }
  }

  @override
  Future<void> write(Credentials credentials) => switch (credentials) {
    NoCredentials() => _storage.delete(key: key),
    _ => _storage.write(key: key, value: jsonEncode(credentials.toJson())),
  };
}

/// Pour les tests.
class MemoryCredentialStore implements CredentialStore {
  MemoryCredentialStore([this.credentials = const NoCredentials()]);

  Credentials credentials;

  @override
  Future<Credentials> read() async => credentials;

  @override
  Future<void> write(Credentials credentials) async => this.credentials = credentials;
}
