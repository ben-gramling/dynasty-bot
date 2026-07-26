output "collector_function_arn" {
  description = "ARN of the collector Lambda (the web task's invoke policy is scoped to this)"
  value       = module.collector.function_arn
}

output "collector_function_name" {
  value = module.collector.function_name
}
