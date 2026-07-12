docker exec -i coolify php artisan tinker <<'EOF'
$app = App\Models\Application::where('uuid', 'kns8oim0f49jourz240dvn8q')->first();
if ($app) {
    echo "Application found: " . $app->name . "\n";
    $cuid = new Visus\Cuid2\Cuid2();
    $res = queue_application_deployment(
        application: $app,
        deployment_uuid: $cuid
    );
    echo "Deployment queued with result: " . json_encode($res) . "\n";
} else {
    echo "Application not found.\n";
}
EOF
