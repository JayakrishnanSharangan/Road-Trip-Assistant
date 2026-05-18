pipeline {
    agent { label 'user-agent' }

    environment {
        APP_NAME = "road-trip-assistant"
        MINIKUBE_HOME = "C:\\Users\\USER"
        KUBECONFIG = "C:\\Users\\USER\\.kube\\config"
    }

    stages {
        stage('Code Validation') {
            steps {
                echo "Validating Python code..."
                bat "python -m py_compile app.py"
            }
        }

        stage('Build Image') {
            steps {
                echo "Building Docker Image..."
                bat "docker build -t ${APP_NAME}:v${BUILD_NUMBER} -t ${APP_NAME}:latest ."
            }
        }

        stage('Cache Sync') {
            steps {
                echo "Syncing local image cache with Minikube..."
                bat "minikube image load ${APP_NAME}:v${BUILD_NUMBER}"
                bat "minikube image load ${APP_NAME}:latest"
            }
        }

        stage('Cluster Rollout') {
            steps {
                echo "Updating deployment with new image..."
                bat "kubectl apply -f k8s/"
                bat "kubectl set image deployment/${APP_NAME} ${APP_NAME}=${APP_NAME}:v${BUILD_NUMBER}"
                bat "kubectl rollout status deployment/${APP_NAME}"
            }
        }
    }

    post {
        failure {
            echo "Deployment failed! Rolling back changes..."
            bat "kubectl rollout undo deployment/${APP_NAME}"
        }
        success {
            echo "Pipeline executed successfully!"
        }
    }
}
