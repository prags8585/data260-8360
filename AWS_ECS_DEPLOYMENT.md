# AWS ECS Deployment Walkthrough (Console)

Config used: `PREFIX = s8360`, app port `8260`, local image `data260-8360-hw1`.

## 1. Push the image to ECR

1. AWS Console → **ECR** → **Repositories** → **Create repository**.
   - Name: `s8360-hw1`
   - Visibility: Private
   - Create.
2. Click into the new repo → **View push commands**. It gives you 4 commands tailored to your account — run them locally in this project folder (`/Users/prags/Desktop/HW1_DATA260`):

```bash
aws ecr get-login-password --region <your-region> | docker login --username AWS --password-stdin <account-id>.dkr.ecr.<your-region>.amazonaws.com
docker tag data260-8360-hw1:latest <account-id>.dkr.ecr.<your-region>.amazonaws.com/s8360-hw1:latest
docker push <account-id>.dkr.ecr.<your-region>.amazonaws.com/s8360-hw1:latest
```

(You'll need the AWS CLI installed and configured with your credentials for the login command: `aws configure`.)

## 2. Create an ECS cluster

1. ECS Console → **Clusters** → **Create cluster**.
   - Name: `data260-8360-cluster`
   - Infrastructure: **AWS Fargate** (serverless — no EC2 instances to manage)
   - Create.

## 3. Register a task definition

1. ECS → **Task definitions** → **Create new task definition**.
   - Family: `data260-8360-hw1-task`
   - Launch type: Fargate
   - CPU: 0.25 vCPU, Memory: 0.5 GB (plenty for a static page)
   - Container:
     - Name: `hw1-app`
     - Image URI: `<account-id>.dkr.ecr.<your-region>.amazonaws.com/s8360-hw1:latest`
     - Container port: `8260`, protocol TCP
   - Create.

## 4. Create a security group for the service

1. EC2 Console → **Security Groups** → **Create security group**.
   - Name: `s8360-hw1-sg`
   - VPC: your default VPC
   - Inbound rule: Custom TCP, port `8260`, source `0.0.0.0/0` (so you can reach it publicly for the screenshot)
   - Create.

## 5. Create the ECS service (one task)

1. Go to your cluster (`data260-8360-cluster`) → **Service** tab → **Create**.
   - Launch type: Fargate
   - Task definition: `data260-8360-hw1-task`, latest revision
   - Service name: `s8360-hw1-service`
   - Desired tasks: **1**
   - Networking: pick a **public subnet**, and check **Auto-assign public IP: ON**
   - Security group: select `s8360-hw1-sg` created above
   - Create.

## 6. Find the public IP and verify

1. Cluster → **Tasks** tab → click the running task.
2. Under **Configuration** → **Network** find the **Public IP**.
3. Open `http://<public-ip>:8260/index.html` in your browser — you should see the same course catalogue form.
4. Take the screenshot for your report here.

## 7. Cleanup (important — avoid ongoing charges)

Once you have your screenshot:

1. ECS → cluster → Service → **Update** → set desired tasks to `0`, or **Delete service**.
2. Delete the cluster.
3. Optionally delete the ECR repository and the security group if you don't need them for later homeworks (note: this same repo is reused all semester per the assignment, so you may want to keep the ECR repo/cluster naming convention around and just scale the service to 0 between homeworks instead of deleting).
