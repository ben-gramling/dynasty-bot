resource "aws_lambda_permission" "allow_cloudwatch" {
  statement_id  = "AllowExecutionFromCloudWatch"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.this.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.invoke_lambda.arn
}

resource "aws_cloudwatch_event_rule" "invoke_lambda" {
  name                = "invoke-${aws_lambda_function.this.function_name}"
  description         = "Invoke Lambda"
  schedule_expression = var.cron_schedule
}

resource "aws_cloudwatch_event_target" "lambda_function_target" {
  target_id = "lambda-function-target"
  rule      = aws_cloudwatch_event_rule.invoke_lambda.name
  arn       = aws_lambda_function.this.arn
}
