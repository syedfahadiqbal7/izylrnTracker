import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_client.dart';
import '../../core/i18n.dart';
import 'auth_controller.dart';
import 'brand_header.dart';

class OtpScreen extends ConsumerStatefulWidget {
  final String phone;
  final String channel;
  const OtpScreen({super.key, required this.phone, required this.channel});
  @override
  ConsumerState<OtpScreen> createState() => _OtpScreenState();
}

class _OtpScreenState extends ConsumerState<OtpScreen> {
  final _otp = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _otp.dispose();
    super.dispose();
  }

  Future<void> _verify() async {
    final t = ref.read(translatorProvider);
    final code = _otp.text.trim();
    if (code.length < 4) {
      setState(() => _error = t.t('auth.enter_code', 'Enter the code we sent you'));
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(authRepositoryProvider).verifyOtp(widget.phone, code);
      await ref.read(authControllerProvider.notifier).loadUser();
      // The router redirect sends us to /home once authenticated.
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } catch (_) {
      setState(() => _error = ref
          .read(translatorProvider)
          .t('common.error_generic', 'Something went wrong. Please try again.'));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _resend() async {
    try {
      await ref.read(authRepositoryProvider).sendOtp(widget.phone);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text(ref
                .read(translatorProvider)
                .t('auth.resent', 'A new code has been sent'))));
      }
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(translatorProvider);
    return Scaffold(
      body: Column(
        children: [
          BrandHeader(
            title: t.t('auth.verify_title', 'Verify your number'),
            subtitle: t.t('auth.verify_sub', 'Enter the 6-digit code'),
          ),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(20, 28, 20, 20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('${t.t('auth.sent_to', 'Sent to')} ${widget.phone}',
                      style: TextStyle(color: Colors.grey.shade700)),
                  if (widget.channel == 'dev') ...[
                    const SizedBox(height: 8),
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: const Color(0xFFFFF7E6),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Text(
                        t.t('auth.dev_hint',
                            'Dev mode: no SMS provider configured — check the backend logs for the code.'),
                        style: const TextStyle(
                            fontSize: 12.5, color: Color(0xFF8A6D1B)),
                      ),
                    ),
                  ],
                  const SizedBox(height: 24),
                  TextField(
                    controller: _otp,
                    keyboardType: TextInputType.number,
                    textAlign: TextAlign.center,
                    maxLength: 6,
                    style: const TextStyle(
                        fontSize: 28,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 12),
                    inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                    decoration: const InputDecoration(
                        counterText: '', hintText: '••••••'),
                    onSubmitted: (_) => _verify(),
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    Text(_error!,
                        style: const TextStyle(
                            color: Colors.red, fontWeight: FontWeight.w500)),
                  ],
                  const SizedBox(height: 24),
                  FilledButton(
                    onPressed: _busy ? null : _verify,
                    child: _busy
                        ? const SizedBox(
                            height: 22,
                            width: 22,
                            child: CircularProgressIndicator(
                                strokeWidth: 2.4, color: Colors.white))
                        : Text(t.t('auth.verify_continue', 'Verify & continue')),
                  ),
                  const SizedBox(height: 8),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      TextButton(
                          onPressed: () => context.go('/login'),
                          child: Text(t.t('auth.change_number', 'Change number'))),
                      TextButton(
                          onPressed: _resend,
                          child: Text(t.t('auth.resend', 'Resend code'))),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
