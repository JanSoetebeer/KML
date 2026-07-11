########################################
# Security group for the web app instance
########################################

resource "aws_security_group" "webapp" {
  name_prefix = "${var.project_name}-webapp-"
  description = "webscraper admin webapp — SSH (restricted), HTTP/HTTPS"
  vpc_id      = data.aws_vpc.default.id

  tags = {
    Name = "${var.project_name}-webapp-sg"
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_ingress_rule" "ssh" {
  security_group_id = aws_security_group.webapp.id
  description       = "SSH"
  cidr_ipv4         = var.ssh_ingress_cidr
  from_port         = 22
  to_port           = 22
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "http" {
  security_group_id = aws_security_group.webapp.id
  description       = "HTTP (Caddy redirects to HTTPS)"
  cidr_ipv4         = var.web_ingress_cidr
  from_port         = 80
  to_port           = 80
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "https" {
  security_group_id = aws_security_group.webapp.id
  description       = "HTTPS"
  cidr_ipv4         = var.web_ingress_cidr
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "all" {
  security_group_id = aws_security_group.webapp.id
  description       = "All outbound"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}
