import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import 'parent_providers.dart';

/// Ouvert par le lien de l'e-mail dans l'application :
/// `ludifun://app/parent/verifier-email?jeton=…` (quel que soit l'espace ouvert sur le téléphone).
class EmailVerificationScreen extends ConsumerStatefulWidget {
  const EmailVerificationScreen({required this.token, super.key});

  final String token;

  @override
  ConsumerState<EmailVerificationScreen> createState() => _EmailVerificationScreenState();
}

class _EmailVerificationScreenState extends ConsumerState<EmailVerificationScreen> {
  late final Future<void> _verification = ref.read(apiProvider).verifyEmail(widget.token).then((_) {
    ref.invalidate(parentProfileProvider);
  });

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Adresse e-mail')),
    body: FutureBuilder<void>(
      future: _verification,
      builder: (context, snapshot) => CenteredBody(
        children: [
          ...switch (snapshot) {
            AsyncSnapshot(connectionState: ConnectionState.waiting) => [
              const Center(child: CircularProgressIndicator()),
            ],
            AsyncSnapshot(:final error?) => [
              ErrorMessage(error is ApiException ? error.message : ApiException.unexpected),
            ],
            _ => [
              const Text('✅', textAlign: TextAlign.center, style: TextStyle(fontSize: 48)),
              const SizedBox(height: 8),
              const Text(
                'Adresse confirmée, merci !',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 20),
              ),
            ],
          },
          const SizedBox(height: 24),
          if (snapshot.connectionState == ConnectionState.done)
            FilledButton(onPressed: () => context.go(Routes.start), child: const Text('Continuer')),
        ],
      ),
    ),
  );
}
