/// Formats de l'API des comptes (§11) : parent, enfants et liaison d'appareil.
library;

typedef Json = Map<String, dynamic>;

class ParentTokens {
  const ParentTokens({
    required this.accessToken,
    required this.refreshToken,
    required this.parentId,
    required this.email,
  });

  factory ParentTokens.fromJson(Json json) {
    final parent = json['parent'] as Json;
    return ParentTokens(
      accessToken: json['access_token'] as String,
      refreshToken: json['refresh_token'] as String,
      parentId: parent['id'] as String,
      email: parent['email'] as String,
    );
  }

  final String accessToken;
  final String refreshToken;
  final String parentId;
  final String email;
}

class Child {
  const Child({
    required this.id,
    required this.displayName,
    required this.grade,
    this.avatar,
    this.devices = 0,
  });

  factory Child.fromJson(Json json) => Child(
    id: json['id'] as String,
    displayName: json['display_name'] as String,
    grade: json['grade'] as String,
    avatar: json['avatar'] as String?,
    devices: json['devices'] as int? ?? 0,
  );

  final String id;
  final String displayName;
  final String grade;
  final String? avatar;

  /// Appareils liés actifs (espace parent uniquement).
  final int devices;
}

class LinkResult {
  const LinkResult({required this.deviceToken, required this.child});

  factory LinkResult.fromJson(Json json) => LinkResult(
    deviceToken: json['token'] as String,
    child: Child.fromJson(json['child'] as Json),
  );

  final String deviceToken;
  final Child child;
}
