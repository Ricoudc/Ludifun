/// L'IA qui lit les photos et crée les jeux, choisie par le parent pour la famille.
library;

import 'account.dart';

class AiProvider {
  const AiProvider({
    required this.code,
    required this.label,
    required this.note,
    required this.needsKey,
    required this.customUrl,
    required this.keyUrl,
    required this.recommended,
    required this.available,
    this.defaultUrl,
    this.defaultModel,
  });

  factory AiProvider.fromJson(Json json) => AiProvider(
    code: json['code'] as String,
    label: json['label'] as String,
    note: json['note'] as String? ?? '',
    needsKey: json['needs_key'] as bool? ?? false,
    customUrl: json['custom_url'] as bool? ?? false,
    keyUrl: json['key_url'] as String? ?? '',
    recommended: json['recommended'] as bool? ?? false,
    available: json['available'] as bool? ?? true,
    defaultUrl: json['default_url'] as String?,
    defaultModel: json['default_model'] as String?,
  );

  final String code;
  final String label;
  final String note;
  final bool needsKey;

  /// Adresse de l'API à indiquer (Ollama, service compatible).
  final bool customUrl;
  final String keyUrl;
  final bool recommended;

  /// Faux : ce serveur refuse ce choix (adresse libre en production).
  final bool available;
  final String? defaultUrl;
  final String? defaultModel;

  /// Clé facultative (service compatible, par exemple Ollama derrière une autre adresse).
  bool get asksKey => needsKey || code == 'compatible';
}

class FamilyAi {
  const FamilyAi({required this.provider, this.model, this.baseUrl, this.keyHint});

  factory FamilyAi.fromJson(Json json) => FamilyAi(
    provider: json['provider'] as String,
    model: json['model'] as String?,
    baseUrl: json['base_url'] as String?,
    keyHint: json['key_hint'] as String?,
  );

  final String provider;
  final String? model;
  final String? baseUrl;

  /// Fin de la clé enregistrée (« …a1b2 ») ; la clé elle-même ne revient jamais.
  final String? keyHint;
}

class AiSettings {
  const AiSettings({required this.family, required this.serverProvider, required this.providers});

  factory AiSettings.fromJson(Json json) => AiSettings(
    family: switch (json['family']) {
      final Json family => FamilyAi.fromJson(family),
      _ => null,
    },
    serverProvider: json['server_provider'] as String,
    providers: [for (final p in json['providers'] as List<dynamic>) AiProvider.fromJson(p as Json)],
  );

  /// `null` : la famille utilise l'IA du serveur.
  final FamilyAi? family;
  final String serverProvider;
  final List<AiProvider> providers;

  AiProvider? provider(String code) => providers.where((p) => p.code == code).firstOrNull;

  String labelOf(String code) => provider(code)?.label ?? code;
}

class AiCheck {
  const AiCheck({required this.ok, required this.message, required this.models});

  factory AiCheck.fromJson(Json json) => AiCheck(
    ok: json['ok'] as bool,
    message: json['message'] as String,
    models: [for (final m in json['models'] as List<dynamic>) m as String],
  );

  final bool ok;
  final String message;
  final List<String> models;
}
