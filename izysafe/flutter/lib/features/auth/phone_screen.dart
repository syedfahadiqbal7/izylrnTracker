import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_client.dart';
import 'auth_controller.dart';
import 'brand_header.dart';

class _Country {
  final String name, dial, flag;
  const _Country(this.name, this.dial, this.flag);
}

const _countries = [
  _Country('India', '+91', '🇮🇳'),
  _Country('UAE', '+971', '🇦🇪'),
];

class PhoneScreen extends ConsumerStatefulWidget {
  const PhoneScreen({super.key});
  @override
  ConsumerState<PhoneScreen> createState() => _PhoneScreenState();
}

class _PhoneScreenState extends ConsumerState<PhoneScreen> {
  _Country _country = _countries.first;
  final _phone = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _phone.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final digits = _phone.text.trim();
    if (digits.isEmpty) {
      setState(() => _error = 'Enter your phone number');
      return;
    }
    final full = '${_country.dial}$digits';
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final channel = await ref.read(authRepositoryProvider).sendOtp(full);
      if (!mounted) return;
      context.go('/otp?phone=${Uri.encodeComponent(full)}&channel=$channel');
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } catch (_) {
      setState(() => _error = 'Something went wrong. Please try again.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: [
          const BrandHeader(
            title: 'Welcome to izyLrn',
            subtitle: 'Keep your children safe, always',
          ),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(20, 28, 20, 20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Sign in',
                      style: Theme.of(context)
                          .textTheme
                          .headlineSmall
                          ?.copyWith(fontWeight: FontWeight.w700)),
                  const SizedBox(height: 6),
                  Text('We’ll send a one-time code to your phone.',
                      style: TextStyle(color: Colors.grey.shade600)),
                  const SizedBox(height: 24),
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 4),
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(14),
                          border:
                              Border.all(color: const Color(0xFFE2E6F0)),
                        ),
                        child: DropdownButtonHideUnderline(
                          child: DropdownButton<_Country>(
                            value: _country,
                            borderRadius: BorderRadius.circular(14),
                            items: _countries
                                .map((c) => DropdownMenuItem(
                                    value: c,
                                    child: Text('${c.flag} ${c.dial}')))
                                .toList(),
                            onChanged: (c) =>
                                setState(() => _country = c ?? _country),
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: TextField(
                          controller: _phone,
                          keyboardType: TextInputType.phone,
                          inputFormatters: [
                            FilteringTextInputFormatter.digitsOnly
                          ],
                          decoration:
                              const InputDecoration(hintText: 'Phone number'),
                          onSubmitted: (_) => _submit(),
                        ),
                      ),
                    ],
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    Text(_error!,
                        style: const TextStyle(
                            color: Colors.red, fontWeight: FontWeight.w500)),
                  ],
                  const SizedBox(height: 24),
                  FilledButton(
                    onPressed: _busy ? null : _submit,
                    child: _busy
                        ? const SizedBox(
                            height: 22,
                            width: 22,
                            child: CircularProgressIndicator(
                                strokeWidth: 2.4, color: Colors.white))
                        : const Text('Send code'),
                  ),
                  const SizedBox(height: 16),
                  Center(
                    child: Text('India & UAE numbers supported',
                        style: TextStyle(
                            color: Colors.grey.shade500, fontSize: 12)),
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
