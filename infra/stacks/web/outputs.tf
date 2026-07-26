output "alb_dns_name" {
  description = "MANUAL STEP - point dynasty.sarikayakomzin.com at this via a CNAME at the external DNS provider"
  value       = aws_lb.web.dns_name
}

output "cognito_hosted_domain" {
  description = "Cognito hosted UI domain prefix (login pages live under this)"
  value       = aws_cognito_user_pool_domain.web.domain
}

output "certificate_arn" {
  description = "The ISSUED ACM cert the listener is using (looked up from the shared stack's cert by domain)"
  value       = data.aws_acm_certificate.web.arn
}
