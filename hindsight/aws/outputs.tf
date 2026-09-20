output "fqdn" {
  value = local.fqdn
}

output "mcp_url" {
  value = "https://${local.fqdn}/mcp"
}

output "public_ip" {
  value = aws_eip.hindsight.public_ip
}

output "instance_id" {
  description = "aws ssm start-session --target <instance_id> で入る"
  value       = aws_instance.hindsight.id
}
